import time
import unittest
from tests.helpers import fixture


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.settings, self.api, self.service = fixture()
        self.problem = self.service.fetch(self.api.hosts)[0]
        self.problem.name = 'F5 Pool /Common/test caído'
        self.problem.severity = 4
        self.problem.suppressed = False
        self.problem.clock = int(time.time()) - 20 * 86400

    def test_high_twenty_days(self):
        self.assertEqual(self.service.reason(self.problem), '')

    def test_high_five_days(self):
        self.problem.clock = int(time.time()) - 5 * 86400
        self.assertIn('antigüedad', self.service.reason(self.problem))

    def test_average_thirty_days(self):
        self.problem.clock = int(time.time()) - 30 * 86400
        self.problem.severity = 3
        self.assertIn('severidad', self.service.reason(self.problem))

    def test_already_suppressed(self):
        self.problem.suppressed = True
        self.assertEqual(self.service.reason(self.problem), 'ya suprimido')

    def test_non_f5(self):
        self.problem.name = 'Pool de base de datos caído'
        self.assertIn('F5', self.service.reason(self.problem))

    def test_tag_and_resource_required(self):
        self.problem.tags = [{'tag': 'vendor', 'value': 'F5'}]
        self.problem.name = 'CPU alta'
        self.assertTrue(self.service.reason(self.problem))
        self.problem.name = 'Pool /Common/backend caído'
        self.assertEqual(self.service.reason(self.problem), '')

    def test_strict_age_boundary(self):
        now = 2_000_000_000
        self.problem.clock = now - 14 * 86400
        self.assertTrue(self.service.reason(self.problem, now))
        self.assertEqual(self.service.reason(self.problem, now + 1), '')

    def test_custom_age(self):
        self.settings.days = 30
        self.assertTrue(self.service.reason(self.problem))

    def test_complete_queries_no_limit(self):
        for n in range(2000):
            self.api.rows.append(dict(self.api.rows[0], eventid=str(1000 + n)))
        results = self.service.fetch(self.api.hosts)
        self.assertEqual(len(results), 2006)
        for method, params in self.api.reads:
            self.assertNotIn('limit', params)
            self.assertFalse(params['recent'])
