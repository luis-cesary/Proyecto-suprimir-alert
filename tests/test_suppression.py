import unittest
from services.suppression import Suppression
from tests.helpers import fixture


class SuppressionTests(unittest.TestCase):
    def setUp(self):
        self.settings, self.api, self.problems = fixture(dry_run=False)
        self.service = Suppression(self.api, self.problems, self.settings)
        self.selected = self.problems.eligible(self.problems.fetch(self.api.hosts))[:1]

    def apply(self, confirmation='APLICAR', permissions=True):
        return self.service.apply(self.selected, self.api.hosts, confirmation, permissions)

    def test_dry_run_zero_writes(self):
        self.settings.dry_run = True
        self.assertIn('SIMULACIÓN', str(self.apply()))
        self.assertEqual(self.api.writes, [])

    def test_wrong_confirmation(self):
        self.apply('aplicar')
        self.assertEqual(self.api.writes, [])

    def test_unconfirmed_permissions(self):
        self.apply(permissions=False)
        self.assertEqual(self.api.writes, [])

    def test_recovers_before_apply(self):
        next(r for r in self.api.rows if r['eventid'] == self.selected[0].eventid)['r_eventid'] = '999'
        self.assertIn('OMITIDO', str(self.apply()))
        self.assertEqual(self.api.writes, [])

    def test_changed_severity_suppression_age_name(self):
        row = next(r for r in self.api.rows if r['eventid'] == self.selected[0].eventid)
        for key, value in [('severity', '3'), ('suppressed', '1'), ('clock', '9999999999'), ('name', 'CPU alta')]:
            original = row[key]
            row[key] = value
            self.assertIn('OMITIDO', str(self.apply()))
            row[key] = original
        self.assertEqual(self.api.writes, [])

    def test_success_verified(self):
        self.assertIn('SUPRIMIDO: estado verificado', str(self.apply()))
        self.assertEqual(self.api.writes, [self.selected[0].eventid])

    def test_api_error_not_success(self):
        self.api.fail_write = True
        self.assertIn('FALLO', str(self.apply()))
        self.assertIn('BLOQUEADO', str(self.apply()))
        self.assertEqual(len(self.api.writes), 1)

    def test_unverified_not_success(self):
        self.api.verify_suppressed = False
        self.assertIn('NO VERIFICADO', str(self.apply()))

    def test_batch_over_limit_zero_writes(self):
        self.selected = self.problems.eligible(self.problems.fetch(self.api.hosts))
        self.assertIn('BLOQUEADO', str(self.apply()))
        self.assertEqual(self.api.writes, [])

    def test_limit_across_menu_operations(self):
        self.apply()
        self.selected = self.problems.eligible(self.problems.fetch(self.api.hosts))[:1]
        self.assertIn('BLOQUEADO', str(self.apply()))
        self.assertEqual(len(self.api.writes), 1)
