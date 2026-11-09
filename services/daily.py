"""Explicitly approved, bounded daily job. No prompt and no implicit scope."""
import json
import os
import re
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import ROOT
from services.groups import Groups
from services.hosts import Hosts
from services.problems import Problems
from services.suppression import Suppression
from utils.validators import ip_networks


def validate_policy(policy, apply=False):
    if not isinstance(policy, dict):
        raise ValueError('automation.json debe contener un objeto.')
    if type(policy.get('enabled')) is not bool or type(policy.get('permissions_verified')) is not bool:
        raise ValueError('enabled y permissions_verified deben ser booleanos.')
    reference = policy.get('approval_reference', '')
    if not isinstance(reference, str) or len(reference) > 200:
        raise ValueError('approval_reference debe ser texto de hasta 200 caracteres.')
    if apply and (not policy['enabled'] or not policy['permissions_verified'] or not reference.strip()):
        raise ValueError('Automatización bloqueada: falta habilitar y documentar aprobación y permisos.')
    cap = policy.get('max_events_per_day')
    if type(cap) is not int or cap < 1:
        raise ValueError('max_events_per_day debe ser un entero positivo.')
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(policy.get('daily_at', ''))):
        raise ValueError('Defina daily_at con la hora aprobada HH:MM de America/Santiago.')
    rules = policy.get('rules')
    if not isinstance(rules, list) or not rules:
        raise ValueError('Debe definir al menos un alcance autorizado en rules.')
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError('Regla inválida.')
        groupid, hostids = rule.get('groupid', ''), rule.get('hostids')
        name = rule.get('group_name', '')
        if not isinstance(groupid, str) or not isinstance(name, str) or bool(groupid) == bool(name.strip()):
            raise ValueError('Cada regla debe indicar groupid o group_name exacto, nunca ambos.')
        if groupid and (not groupid.isdigit() or groupid == '0'):
            raise ValueError('groupid debe ser un ID válido.')
        selector = ('id', groupid) if groupid else ('name', name.strip().casefold())
        if selector in seen:
            raise ValueError('No repita un grupo en la política.')
        seen.add(selector)
        if not isinstance(hostids, list) or any(not isinstance(h, str) or not h.isdigit() or h == '0' for h in hostids):
            raise ValueError('hostids debe ser una lista de IDs reales.')
        all_hosts = rule.get('all_hosts_in_group')
        if type(all_hosts) is not bool or (not hostids and not all_hosts) or (hostids and all_hosts):
            raise ValueError('Indique hostids explícitos o all_hosts_in_group=true, nunca ambos.')
        if type(rule.get('days')) is not int or not 1 <= rule['days'] <= 36500:
            raise ValueError('Días aprobados inválidos.')
        if type(rule.get('min_severity')) is not int or rule['min_severity'] not in range(6):
            raise ValueError('Severidad aprobada inválida.')
        ips = rule.get('include_ips', [])
        if not isinstance(ips, list) or any(not isinstance(ip, str) or not ip.strip() for ip in ips):
            raise ValueError('include_ips debe ser una lista de IP o CIDR; [] selecciona todas.')
        for ip in ips:
            ip_networks(ip)
    return policy


@contextmanager
def process_lock(path):
    """OS lock released automatically on crashes. Never delete lock files."""
    path.parent.mkdir(exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Ya existe una ejecución diaria activa.') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class DailyRunner:
    def __init__(self, api, settings, state_dir=None, audit=None, today=None):
        self.api, self.settings = api, settings
        self.directory = Path(state_dir) if state_dir else ROOT / 'runtime'
        self.audit = audit or (lambda **record: None)
        self.today = today or (lambda: datetime.now(ZoneInfo('America/Santiago')).date().isoformat())

    def save(self, ledger):
        temporary = self.directory / 'daily_state.tmp'
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(ledger, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.directory / 'daily_state.json')
        if os.name != 'nt':
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def run(self, policy, apply=False):
        validate_policy(policy, apply)
        if apply and self.settings.dry_run:
            raise ValueError('DRY_RUN=true: no se puede ejecutar --apply.')
        with process_lock(self.directory / 'daily.lock'):
            path = self.directory / 'daily_state.json'
            ledger = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'events': {}, 'days': {}}
            if not isinstance(ledger, dict) or not isinstance(ledger.get('events'), dict) or not isinstance(ledger.get('days'), dict):
                raise ValueError('Estado diario inválido; no se realizan escrituras.')
            day = self.today()
            used = ledger['days'].get(day, 0)
            if type(used) is not int or used < 0:
                raise ValueError('Contador diario inválido; revisar estado.')
            remaining = max(0, policy['max_events_per_day'] - used)
            groups = {g['groupid']: g for g in Groups(self.api).list()}
            candidates = {}
            resolved = set()
            # Resolve every rule before writing anything; missing scope aborts the job.
            for rule in policy['rules']:
                groupid = rule.get('groupid', '')
                if not groupid:
                    matches = [g for g in groups.values() if g['name'].strip().casefold() == rule['group_name'].strip().casefold()]
                    if len(matches) != 1:
                        raise ValueError('El nombre del grupo debe coincidir con un único grupo accesible: ' + rule['group_name'])
                    groupid = matches[0]['groupid']
                if groupid not in groups or groupid in resolved:
                    raise ValueError('Grupo autorizado inexistente, repetido o sin acceso: ' + groupid)
                resolved.add(groupid)
                hosts = Hosts(self.api).list(groupid)
                if not rule['all_hosts_in_group']:
                    hosts = [h for h in hosts if h['hostid'] in rule['hostids']]
                    if {h['hostid'] for h in hosts} != set(rule['hostids']):
                        raise ValueError('Algún host autorizado ya no pertenece al grupo o no es accesible.')
                if rule.get('include_ips'):
                    hosts = Hosts.filter_ips(hosts, ','.join(rule['include_ips']))
                scoped = replace(self.settings, days=rule['days'], severity=rule['min_severity'],
                                 severity_at_least=True, dry_run=not apply)
                service = Problems(self.api, scoped)
                for problem in service.eligible(service.fetch(hosts)):
                    # Ignore any previous attempt, including unknown outcome after a crash.
                    if problem.eventid not in ledger['events']:
                        candidates.setdefault(problem.eventid, (problem, hosts, scoped, groups[groupid]['name']))
            ordered = sorted(candidates.values(), key=lambda item: (item[0].clock, int(item[0].eventid)))
            result = {}
            for problem, hosts, scoped, group in ordered:
                if remaining <= 0:
                    break
                eventid = problem.eventid
                if not apply:
                    result[eventid] = 'PLAN: elegible; no se modifica Zabbix'
                    remaining -= 1
                else:
                    reference = policy['approval_reference'].strip()
                    scoped = replace(scoped, suppression_message=scoped.suppression_message + ' Referencia: ' + reference)

                    def reserve(eid):
                        ledger['days'][day] = ledger['days'].get(day, 0) + 1
                        ledger['events'][eid] = {'day': day, 'result': 'INTENTO: resultado pendiente', 'approval': reference}
                        self.save(ledger)  # Durable reservation BEFORE the API request.
                        self.audit(operation='AUTO INTENTO', eventid=eid, group=group,
                                   host=', '.join(h['host'] for h in problem.hosts), problem=problem.name,
                                   result='Supresión con mensaje; aprobación: ' + reference)

                    writer = Suppression(self.api, Problems(self.api, scoped), scoped, before_write=reserve)
                    result.update(writer.apply([problem], hosts, 'APLICAR', True))
                    remaining -= writer.attempted
                    if eventid in ledger['events']:
                        ledger['events'][eventid]['result'] = result[eventid]
                        self.save(ledger)
                self.audit(operation='AUTO RESULTADO' if apply else 'AUTO PLAN', eventid=eventid,
                           host=', '.join(h['host'] for h in problem.hosts), problem=problem.name,
                           group=group, result=result[eventid])
            self.audit(operation='AUTO FIN', result='%d candidatos; %d resultados; %d cupos restantes' % (len(ordered), len(result), remaining))
            return result
