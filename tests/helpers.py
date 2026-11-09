import time
from config.settings import Settings
from services.demo import DemoAPI
from services.problems import Problems
from services.zabbix_api import APIError


class FakeAPI(DemoAPI):
    def __init__(self):
        super().__init__()
        self.reads, self.writes = [], []
        self.fail_write = False
        self.verify_suppressed = True

    def call(self, method, params):
        self.reads.append((method, params))
        return super().call(method, params)

    def suppress(self, eventid, **kwargs):
        self.writes.append(eventid)
        if self.fail_write:
            raise APIError('Fallo simulado')
        if self.verify_suppressed:
            row = next(r for r in self.rows if r['eventid'] == eventid)
            row['suppressed'] = '1'
            row.setdefault('acknowledges', []).append({'action': '36', 'message': kwargs.get('message', '')})
        return {'eventids': [eventid]}


def fixture(dry_run=True):
    settings = Settings(dry_run=dry_run)
    api = FakeAPI()
    service = Problems(api, settings)
    return settings, api, service
