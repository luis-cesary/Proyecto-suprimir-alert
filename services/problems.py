import logging
import re
import time
from server.alertas.models import Problem
from config.settings import SEVERITIES

log = logging.getLogger('zabbix')


class Problems:
    def __init__(self, api, settings):
        self.api, self.settings = api, settings

    def fetch(self, hosts, eventids=None):
        # Full query per host: exact association, no unsupported selectHosts on problem.get,
        # no limit that could silently omit older events. Deduplicate cross-host triggers.
        found = {}
        for host in hosts:
            params = {'output': ['eventid', 'name', 'clock', 'severity', 'acknowledged',
                                 'suppressed', 'r_eventid', 'objectid'],
                      'hostids': [host['hostid']], 'source': 0, 'object': 0,
                      'recent': False, 'selectTags': 'extend', 'selectSuppressionData': 'extend',
                      'selectAcknowledges': ['action', 'message']}
            if eventids is not None:
                if not eventids:
                    return []
                params['eventids'] = list(eventids)
            for row in self.api.call('problem.get', params):
                problem = Problem.from_api(row, host)
                if problem.eventid in found:
                    found[problem.eventid].hosts.append(host)
                else:
                    found[problem.eventid] = problem
        log.debug('Problemas abiertos consultados=%d', len(found))
        return sorted(found.values(), key=lambda p: (p.clock, int(p.eventid)))

    def reason(self, problem, now=None):
        now = time.time() if now is None else now
        if problem.recovered:
            return 'recuperado'
        if self.settings.severity_at_least and problem.severity < self.settings.severity:
            return 'severidad inferior a ' + SEVERITIES[self.settings.severity]
        if not self.settings.severity_at_least and problem.severity != self.settings.severity:
            log.debug('Evento=%s severidad distinta de %s', problem.eventid, SEVERITIES[self.settings.severity])
            return 'severidad distinta de ' + SEVERITIES[self.settings.severity]
        if problem.suppressed:
            return 'ya suprimido'
        if problem.age(now) <= self.settings.days:
            return 'antigüedad insuficiente'
        name_match = any(re.search(pattern, problem.name) for pattern in self.settings.patterns)
        tag_match = any(t.get('tag', '').casefold() == key.casefold() and
                        t.get('value', '').casefold() == value.casefold()
                        for t in problem.tags for key, value in self.settings.tags)
        if not name_match and not (tag_match and re.search(self.settings.resource_pattern, problem.name)):
            return 'fuera del alcance F5 Pool/VS'
        return ''

    def eligible(self, problems):
        now = time.time()
        result = []
        for problem in problems:
            reason = self.reason(problem, now)
            log.debug('Evento=%s días=%.4f resultado=%s', problem.eventid, problem.age(now), reason or 'elegible')
            if not reason:
                result.append(problem)
        return result
