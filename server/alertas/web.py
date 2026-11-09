"""Loopback-only MVC web adapter. No accounts, database or external assets.

All requests accessing API/state serialize under one lock. The write budget is
global to this server process, not reset by new tabs, cookies or browser sessions.
"""
import csv
import io
import json
import logging
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cli.tables import HEADERS, problem_rows
from config.settings import ROOT, SEVERITIES
from server.alertas.managers import AlertManager
from services.problems import Problems
from services.zabbix_api import APIError
from utils.logger import LOG_PATH

ASSETS = Path(__file__).parent / 'views' / 'web'
log = logging.getLogger('zabbix')


class WebApp:
    def __init__(self, api, settings, version, demo=False, audit_path=None):
        self.api, self.settings, self.version, self.demo = api, settings, version, demo
        self.manager = AlertManager(api, settings)
        self.lock = threading.RLock()
        self.sessions = {}
        self.audit_path = Path(audit_path) if audit_path else ROOT / 'logs' / 'web_audit.jsonl'

    def session(self, cookie):
        jar = SimpleCookie()
        try:
            jar.load(cookie or '')
        except Exception:
            jar = SimpleCookie()
        sid = jar['zbx_session'].value if 'zbx_session' in jar else ''
        now = time.time()
        self.sessions = {key: value for key, value in self.sessions.items() if now - value['last'] < 7200}
        if sid not in self.sessions:
            if len(self.sessions) >= 100:
                raise ValueError('Demasiadas sesiones locales abiertas.')
            sid = secrets.token_urlsafe(32)
            self.sessions[sid] = {'csrf': secrets.token_urlsafe(32), 'snapshot': '',
                                  'rows': [], 'hosts': [], 'group': {}, 'days': self.settings.days,
                                  'severity': self.settings.severity}
        self.sessions[sid]['last'] = now
        return sid, self.sessions[sid]

    def redact(self, value):
        text = str(value)
        return text.replace(self.settings.token, '[REDACTADO]') if self.settings.token else text

    def audit(self, operation, eventid='', host='', problem='', result='', group=''):
        record = {'time': datetime.now(timezone.utc).isoformat(), 'operation': operation,
                  'eventid': eventid, 'host': host, 'problem': problem, 'result': result,
                  'group': group, 'mode': 'DEMO' if self.demo else ('SIMULACIÓN' if self.settings.dry_run else 'REAL')}
        record = {key: self.redact(value) for key, value in record.items()}
        self.audit_path.parent.mkdir(exist_ok=True)
        with self.audit_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        log.info('WEB operación=%s evento=%s resultado=%s', record['operation'], record['eventid'], record['result'])
        return record

    def history(self):
        if not self.audit_path.exists():
            return []
        records = []
        with self.audit_path.open(encoding='utf-8') as stream:
            for line in deque(stream, maxlen=200):
                try:
                    records.append(json.loads(self.redact(line)))
                except ValueError:
                    continue
        return list(reversed(records))

    def state(self, session):
        return {'version': self.version, 'demo': self.demo, 'dry_run': self.settings.dry_run,
                'days': self.settings.days, 'severity': self.settings.severity, 'csrf': session['csrf'],
                'suppression_message': self.settings.suppression_message,
                'limit': self.settings.max_write_events,
                'remaining': max(0, self.settings.max_write_events - self.manager.suppression.attempted),
                'default_group': self.settings.group}

    @staticmethod
    def ids(value):
        if not isinstance(value, list) or not value or len(value) > 10000:
            raise ValueError('Seleccione al menos un elemento.')
        if any(not isinstance(i, str) or not i.isdigit() for i in value):
            raise ValueError('Los identificadores deben ser numéricos.')
        return list(dict.fromkeys(value))

    def invalidate(self, session):
        session.update(snapshot='', rows=[], hosts=[], group={})

    def query(self, session, data):
        self.invalidate(session)
        groups = self.manager.groups.list()
        group = next((g for g in groups if g['groupid'] == data.get('groupid')), None)
        if not group:
            raise ValueError('Grupo inexistente o sin acceso.')
        ids = self.ids(data.get('hostids'))
        hosts = self.manager.hosts.list(group['groupid'])
        selected = [h for h in hosts if h['hostid'] in ids]
        if {h['hostid'] for h in selected} != set(ids):
            raise ValueError('La selección incluye equipos fuera del grupo o sin acceso.')
        days = data.get('days')
        if type(days) is not int or not 1 <= days <= 36500:
            raise ValueError('La antigüedad debe ser un entero entre 1 y 36500 días.')
        severity = data.get('severity', self.settings.severity)
        if type(severity) is not int or severity not in range(6):
            raise ValueError('Seleccione una severidad válida entre 0 y 5.')
        service = Problems(self.api, replace(self.settings, days=days, severity=severity))
        rows = service.fetch(selected)
        eligible = {p.eventid for p in service.eligible(rows)}
        now = time.time()
        result = [{'eventid': p.eventid, 'name': p.name, 'hosts': ', '.join(h['host'] for h in p.hosts),
                   'started': p.started, 'days': round(p.age(now), 2), 'severity': p.severity,
                   'acknowledged': p.acknowledged, 'suppressed': p.suppressed,
                   'eligible': p.eventid in eligible, 'reason': service.reason(p, now) or 'Elegible'} for p in rows]
        self.audit('CONSULTA', group=group['name'], result='%d abiertos; %d elegibles; >%d días; severidad=%s' % (len(rows), len(eligible), days, SEVERITIES[severity]))
        session.update(rows=rows, hosts=selected, group=group, days=days, severity=severity, snapshot=secrets.token_urlsafe(24))
        return {'problems': result, 'snapshot': session['snapshot'], 'queried_at': datetime.now(timezone.utc).isoformat()}

    def suppress(self, session, data):
        if not session['snapshot'] or not secrets.compare_digest(str(data.get('snapshot', '')), session['snapshot']):
            raise ValueError('Consulta vencida o ya utilizada. Vuelva a consultar alertas.')
        ids = self.ids(data.get('eventids'))
        service = Problems(self.api, replace(self.settings, days=session['days'], severity=session['severity']))
        eligible = {p.eventid: p for p in service.eligible(session['rows'])}
        if any(i not in eligible for i in ids):
            raise ValueError('Solo puede seleccionar eventos elegibles de la consulta actual.')
        selected = [eligible[i] for i in ids]
        # Consume snapshot before the first operation: an uncertain client retry cannot write again.
        session['snapshot'] = ''
        for p in selected:
            self.audit('SOLICITUD', p.eventid, ', '.join(h['host'] for h in p.hosts), p.name,
                       'Selección recibida; severidad=%s; aún sin resultado' % SEVERITIES[session['severity']], session['group']['name'])
        writer = self.manager.suppression
        writer.problems = service
        result = writer.apply(selected, session['hosts'], data.get('confirmation', ''),
                              data.get('permissions') == 'PERMISOS VERIFICADOS')
        for p in selected:
            self.audit('RESULTADO', p.eventid, ', '.join(h['host'] for h in p.hosts), p.name,
                       result[p.eventid], session['group']['name'])
        return {'results': result, 'state': self.state(session)}

    def csv(self, session):
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        service = Problems(self.api, replace(self.settings, days=session['days'], severity=session['severity']))
        for row in problem_rows(session['rows'], service):
            values = []
            for value in row:
                text = self.redact(value)
                values.append("'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text)
            writer.writerow(values)
        return ('\ufeff' + output.getvalue()).encode('utf-8')


class WebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, app, port=8080):
        self.app = app
        super().__init__(('127.0.0.1', port), WebHandler)


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log arbitrary URL query strings, cookies or request headers.
        pass

    def send(self, status, body, content_type='application/json; charset=utf-8', cookie=None, download=False):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', 'zbx_session=%s; HttpOnly; SameSite=Strict; Path=/' % cookie)
        if download:
            self.send_header('Content-Disposition', 'attachment; filename="alertas.csv"')
        self.end_headers()
        self.wfile.write(body)

    def trusted_host(self):
        port = self.server.server_port
        return self.headers.get('Host') in ('127.0.0.1:%d' % port, 'localhost:%d' % port)

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        if not self.trusted_host():
            self.send(403, {'error': 'Host no permitido; use localhost o 127.0.0.1.'})
            return
        app = self.server.app
        try:
            with app.lock:
                sid, session = app.session(self.headers.get('Cookie'))
                url = urlsplit(self.path)
                if not post and url.path in ('/', '/app.js', '/style.css'):
                    name, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                                  '/style.css': ('style.css', 'text/css')}[url.path]
                    self.send(200, (ASSETS / name).read_bytes(), mime + '; charset=utf-8', sid)
                    return
                if post:
                    origin = self.headers.get('Origin')
                    expected = 'http://' + self.headers['Host']
                    if origin != expected or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                        self.send(403, {'error': 'Origen o sesión inválida. Recargue la página.'})
                        return
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 200000 or self.headers.get('Content-Type') != 'application/json':
                        raise ValueError('Solicitud JSON inválida o demasiado grande.')
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError('Se esperaba un objeto JSON.')
                    if url.path == '/api/query':
                        result = app.query(session, data)
                    elif url.path == '/api/suppress':
                        result = app.suppress(session, data)
                    elif url.path == '/api/invalidate':
                        app.invalidate(session)
                        result = {'ok': True}
                    elif url.path == '/api/filter-hosts':
                        groupid = str(data.get('groupid', ''))
                        if not groupid.isdigit():
                            raise ValueError('Seleccione un grupo válido.')
                        hosts = app.manager.hosts.list(groupid)
                        matched = app.manager.hosts.filter_ips(hosts, str(data.get('filter', '')))
                        result = {'hostids': [h['hostid'] for h in matched]}
                    else:
                        self.send(404, {'error': 'Ruta no encontrada.'})
                        return
                elif url.path == '/api/state':
                    result = app.state(session)
                elif url.path == '/api/groups':
                    result = app.manager.groups.list(parse_qs(url.query).get('q', [''])[0])
                elif url.path == '/api/hosts':
                    groupid = parse_qs(url.query).get('groupid', [''])[0]
                    if not groupid.isdigit():
                        raise ValueError('Seleccione un grupo válido.')
                    result = app.manager.hosts.list(groupid)
                elif url.path == '/api/activity':
                    lines = []
                    if LOG_PATH.exists():
                        with LOG_PATH.open(encoding='utf-8') as stream:
                            lines = [app.redact(line.rstrip()) for line in deque(stream, maxlen=100)]
                    result = {'history': app.history(), 'logs': lines}
                elif url.path == '/api/export':
                    self.send(200, app.csv(session), 'text/csv; charset=utf-8', sid, download=True)
                    return
                else:
                    self.send(404, {'error': 'Ruta no encontrada.'})
                    return
                self.send(200, result, cookie=sid)
        except (APIError, ValueError) as exc:
            self.send(400, {'error': app.redact(exc)})
        except (OSError, KeyError, TypeError):
            log.error('WEB error interno de datos/archivos; no se asume éxito de operaciones pendientes')
            self.send(500, {'error': 'No fue posible completar la operación. Revise logs y estado en Zabbix; no reintente una escritura sin verificar.'})


def serve(api, settings, version, demo=False, port=8080):
    if not 1 <= port <= 65535:
        raise ValueError('Puerto inválido.')
    server = WebServer(WebApp(api, settings, version, demo), port)
    print('Vista web: http://127.0.0.1:%d — Ctrl+C para detener.' % port, flush=True)
    print('Acceso remoto mediante túnel SSH; el servidor solo escucha en loopback.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServidor web detenido.')
    finally:
        server.server_close()
