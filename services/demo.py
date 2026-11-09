"""In-memory fictional data. No transport and no production token required."""
import copy
import logging
import time
from services.zabbix_api import APIError


class DemoAPI:
    def __init__(self):
        self.groups = [{'groupid': '101', 'name': 'Banco estado (DEMO)'},
                       {'groupid': '102', 'name': 'Sin equipos (DEMO)'}]
        self.hosts = [
            {'hostid': '201', 'host': 'F51-DEMO', 'name': 'F5 laboratorio 1', 'status': '0',
             'interfaces': [{'ip': '192.0.2.10', 'dns': '', 'useip': '1'},
                            {'ip': '2001:db8::10', 'dns': '', 'useip': '1'}]},
            {'hostid': '202', 'host': 'F52-DEMO', 'name': 'F5 laboratorio DNS', 'status': '0',
             'interfaces': [{'ip': '', 'dns': 'f5.example.invalid', 'useip': '0'}]},
            {'hostid': '203', 'host': 'F53-DEMO', 'name': 'F5 deshabilitado', 'status': '1',
             'interfaces': []}]
        self.rows = []
        for n, (age, severity, suppressed, name) in enumerate([
            (35, 4, '0', 'F5 Pool /Common/pool_demo no disponible'),
            (22, 4, '0', 'F5 VS /Common/vs_demo no disponible'),
            (5, 4, '0', 'F5 Pool /Common/pool_nuevo no disponible'),
            (30, 3, '0', 'F5 Pool /Common/pool_average no disponible'),
            (40, 4, '1', 'F5 Pool /Common/pool_suprimido no disponible'),
            (40, 4, '0', 'CPU alta')], 1):
            self.rows.append({'eventid': str(300 + n), 'name': name,
                              'clock': str(int(time.time()) - age * 86400),
                              'severity': str(severity), 'suppressed': suppressed,
                              'r_eventid': '0', 'acknowledged': '1' if n == 2 else '0',
                              'tags': [], 'objectid': str(400 + n),
                              '_hostid': '201' if n % 2 else '202'})

    def connect(self):
        return '7.4.16 (DEMO sin conexión)'

    def call(self, method, params):
        logging.getLogger('zabbix').debug('DEMO método=%s parámetros=%s', method, params)
        if method == 'hostgroup.get':
            needle = params.get('search', {}).get('name', '').casefold()
            return copy.deepcopy([g for g in self.groups if needle in g['name'].casefold()])
        if method == 'host.get':
            return copy.deepcopy(self.hosts if params['groupids'] == ['101'] else [])
        if method == 'problem.get':
            return copy.deepcopy([p for p in self.rows if p['_hostid'] in params['hostids']
                                  and (not params.get('eventids') or p['eventid'] in params['eventids'])
                                  and p['r_eventid'] == '0'])
        raise APIError('Método no disponible en demo.')

    def suppress(self, *args, **kwargs):
        raise APIError('La demo nunca permite escrituras.')
