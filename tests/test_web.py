import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from config.settings import ROOT
from server.alertas.web import WebApp, WebHandler
from tests.helpers import fixture


class MemorySocket:
    """Exercise the real HTTP parser/handler without sockets or external access."""
    def __init__(self, request):
        self.request = io.BytesIO(request)
        self.response = bytearray()

    def makefile(self, *args, **kwargs):
        return self.request

    def sendall(self, data):
        self.response.extend(data)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(self.temp.cleanup)
        self.settings, self.api, _ = fixture()
        self.path = Path(self.temp.name) / 'audit.jsonl'
        self.app = WebApp(self.api, self.settings, '7.4.16 DEMO', True, self.path)
        self.sid, self.session = self.app.session('')

    def query(self, session=None, **extra):
        return self.app.query(session or self.session, dict(groupid='101', hostids=['201', '202'], days=14, **extra))

    def apply(self, session=None, **overrides):
        session = session or self.session
        payload = {'snapshot': session['snapshot'], 'eventids': ['301'], 'confirmation': 'APLICAR',
                   'permissions': 'PERMISOS VERIFICADOS'}
        payload.update(overrides)
        return self.app.suppress(session, payload)

    def request(self, path, method='GET', data=None, host='127.0.0.1:8080', csrf=None, origin=None):
        payload = json.dumps(data).encode() if data is not None else b''
        headers = [f'{method} {path} HTTP/1.1', f'Host: {host}', f'Cookie: zbx_session={self.sid}',
                   'Content-Type: application/json', f'Content-Length: {len(payload)}']
        if csrf is not None:
            headers.append('X-CSRF-Token: ' + csrf)
        if origin is not None:
            headers.append('Origin: ' + origin)
        socket = MemorySocket(('\r\n'.join(headers) + '\r\n\r\n').encode() + payload)
        WebHandler(socket, ('127.0.0.1', 12345), SimpleNamespace(server_port=8080, app=self.app))
        head, body = bytes(socket.response).split(b'\r\n\r\n', 1)
        return int(head.split(b' ')[1]), head, body

    def test_query_and_eligibility(self):
        result = self.query()
        self.assertEqual(len(result['problems']), 6)
        self.assertEqual(sum(p['eligible'] for p in result['problems']), 2)
        self.assertEqual(self.app.history()[0]['operation'], 'CONSULTA')

    def test_dry_run_has_audited_result_zero_writes(self):
        self.query()
        result = self.apply()
        self.assertIn('SIMULACIÓN', result['results']['301'])
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.app.history()[0]['eventid'], '301')
        self.assertEqual(self.app.history()[0]['mode'], 'DEMO')

    def test_audit_persists_between_instances(self):
        self.query()
        other = WebApp(self.api, self.settings, '7.4.16', audit_path=self.path)
        self.assertEqual(len(other.history()), 1)

    def test_replay_blocked(self):
        self.query()
        snapshot = self.session['snapshot']
        self.apply()
        with self.assertRaisesRegex(ValueError, 'utilizada'):
            self.apply(snapshot=snapshot)
        self.assertEqual(self.api.writes, [])

    def test_forged_event_rejected(self):
        self.query()
        for ids in (['999'], ['303'], ['304'], ['305'], ['306']):
            with self.assertRaises(ValueError):
                self.apply(eventids=ids)
        self.assertEqual(self.api.writes, [])

    def test_query_rejects_hosts_outside_group(self):
        with self.assertRaises(ValueError):
            self.app.query(self.session, {'groupid': '102', 'hostids': ['201'], 'days': 14})

    def test_failed_query_clears_previous_snapshot(self):
        self.query()
        with self.assertRaises(ValueError):
            self.app.query(self.session, {'groupid': '999', 'hostids': ['201'], 'days': 14})
        self.assertEqual(self.session['snapshot'], '')
        self.assertEqual(self.session['rows'], [])

    def test_invalid_days(self):
        for days in (0, -1, '14', True, 40000):
            with self.assertRaises(ValueError):
                self.app.query(self.session, {'groupid': '101', 'hostids': ['201'], 'days': days})

    def test_severity_selection_changes_eligibility(self):
        result = self.query(severity=3)
        self.assertEqual([p['eventid'] for p in result['problems'] if p['eligible']], ['304'])
        self.assertIn('severidad=Average', self.app.history()[0]['result'])
        self.assertIn('Elegible', self.app.csv(self.session).decode('utf-8-sig'))

    def test_invalid_severity(self):
        for severity in (-1, 6, '4', True, None):
            with self.assertRaises(ValueError):
                self.query(severity=severity)

    def test_selected_severity_revalidated_before_write(self):
        self.settings.dry_run = False
        self.query(severity=3)
        next(r for r in self.api.rows if r['eventid'] == '304')['severity'] = '4'
        result = self.apply(eventids=['304'])
        self.assertIn('OMITIDO', result['results']['304'])
        self.assertEqual(self.api.writes, [])

    def test_selected_severity_real_flow_uses_snapshot_not_submission(self):
        self.settings.dry_run = False
        self.query(severity=3)
        result = self.apply(eventids=['304'], severity=4)
        self.assertIn('SUPRIMIDO', result['results']['304'])
        self.assertEqual(self.api.writes, ['304'])

    def test_severity_isolated_between_browser_sessions(self):
        self.query(severity=3)
        _, other = self.app.session('')
        self.query(other)
        self.assertEqual(self.session['severity'], 3)
        self.assertEqual(other['severity'], 4)

    def test_sessions_are_isolated(self):
        self.query()
        _, other = self.app.session('')
        with self.assertRaises(ValueError):
            self.apply(other, snapshot=self.session['snapshot'])

    def test_shared_real_write_budget(self):
        self.settings.dry_run = False
        self.query()
        self.assertIn('SUPRIMIDO', self.apply()['results']['301'])
        _, second = self.app.session('')
        self.query(second)
        result = self.apply(second, eventids=['302'])
        self.assertIn('BLOQUEADO', result['results']['302'])
        self.assertEqual(self.api.writes, ['301'])

    def test_real_recovery_revalidated(self):
        self.settings.dry_run = False
        self.query()
        self.api.rows[0]['r_eventid'] = '999'
        self.assertIn('OMITIDO', self.apply()['results']['301'])
        self.assertEqual(self.api.writes, [])

    def test_wrong_confirmation_and_permissions_no_writes(self):
        self.settings.dry_run = False
        self.query()
        self.assertIn('CANCELADO', self.apply(confirmation='no')['results']['301'])
        self.query()
        self.assertIn('BLOQUEADO', self.apply(permissions='')['results']['301'])
        self.assertEqual(self.api.writes, [])

    def test_csv_and_formula_injection(self):
        self.query()
        self.session['rows'][0].name = '=FORMULA()'
        content = self.app.csv(self.session).decode('utf-8-sig')
        self.assertIn("'=FORMULA()", content)
        self.assertIn('Event ID', content)

    def test_get_assets_state_and_activity(self):
        for path in ('/', '/app.js', '/style.css', '/api/state', '/api/activity'):
            status, headers, _ = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(b'Cache-Control: no-store', headers)
            self.assertIn(b'Content-Security-Policy:', headers)

    def test_get_cannot_suppress(self):
        self.assertEqual(self.request('/api/suppress')[0], 404)
        self.assertEqual(self.api.writes, [])

    def test_csrf_and_origin_guard(self):
        for csrf, origin in [(None, None), (self.session['csrf'], 'https://evil.invalid'),
                             ('bad', 'http://127.0.0.1:8080')]:
            status, _, _ = self.request('/api/suppress', 'POST', {}, csrf=csrf, origin=origin)
            self.assertEqual(status, 403)
        self.assertEqual(self.api.writes, [])

    def test_host_guard(self):
        self.assertEqual(self.request('/api/state', host='evil.invalid:8080')[0], 403)

    def test_http_query_and_suppress(self):
        status, _, body = self.request('/api/query', 'POST', {'groupid': '101', 'hostids': ['201'], 'days': 14},
                                       csrf=self.session['csrf'], origin='http://127.0.0.1:8080')
        self.assertEqual(status, 200)
        snapshot = json.loads(body)['snapshot']
        status, _, body = self.request('/api/suppress', 'POST', {'snapshot': snapshot, 'eventids': ['301'], 'confirmation': 'APLICAR'},
                                       csrf=self.session['csrf'], origin='http://127.0.0.1:8080')
        self.assertEqual(status, 200)
        self.assertIn('SIMULACIÓN', json.loads(body)['results']['301'])

    def test_no_arbitrary_file_serving_or_secret_state(self):
        self.settings.token = 'secret-unique-test'
        self.assertEqual(self.request('/config.env')[0], 404)
        self.assertEqual(self.request('/../../config.env')[0], 404)
        self.assertNotIn(b'secret-unique-test', self.request('/api/state')[2])
        self.app.audit('TEST', result='secret-unique-test')
        self.assertNotIn('secret-unique-test', self.path.read_text())
