import logging
from utils.validators import ip_networks, matches_ips


class Hosts:
    def __init__(self, api):
        self.api = api

    def list(self, groupid):
        rows = self.api.call('host.get', {
            'groupids': [groupid], 'output': ['hostid', 'host', 'name', 'status'],
            'selectInterfaces': ['ip', 'dns', 'useip', 'main', 'type'], 'sortfield': 'name'})
        logging.getLogger('zabbix').debug('Hosts encontrados=%d interfaces=%s', len(rows), rows)
        return rows

    @staticmethod
    def filter_ips(rows, text, exclude=False):
        networks = ip_networks(text)
        return [h for h in rows if matches_ips(h, networks) != exclude]
