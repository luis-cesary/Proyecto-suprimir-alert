import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import ROOT
from services.daily import DailyRunner, process_lock, validate_policy
from services.suppression import Suppression
from tests.helpers import fixture


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(self.temp.cleanup)
        self.settings, self.api, self.problems = fixture(dry_run=False)
        self.records = []
        self.date = '2026-11-09'
        self.runner = DailyRunner(self.api, self.settings, self.temp.name,
                                  audit=lambda **r: self.records.append(r), today=lambda: self.date)
        self.policy = {'enabled': True, 'permissions_verified': True, 'approval_reference': 'Aprobación de prueba',
                       'daily_at': '00:01', 'max_events_per_day': 100,
                       'rules': [{'groupid': '101', 'hostids': [], 'all_hosts_in_group': True,
                                  'include_ips': [], 'days': 14, 'min_severity': 4}]}

    def test_plan_never_writes_or_consumes_daily_budget(self):
        result = self.runner.run(self.policy)
        self.assertEqual(set(result), {'301', '302'})
        self.assertEqual(self.api.writes, [])
        self.assertFalse((Path(self.temp.name) / 'daily_state.json').exists())

    def test_high_and_disaster_but_not_average(self):
        self.api.rows[1]['severity'] = '5'
        result = self.runner.run(self.policy, apply=True)
        self.assertEqual(set(result), {'301', '302'})
        self.assertTrue(all('mensaje registrado' in r for r in result.values()))
        self.assertEqual(self.api.rows[1]['acknowledged'], '1')
        self.assertEqual(self.api.rows[0]['acknowledged'], '0')

    def test_cap_survives_restart_and_new_day_allows_other_events(self):
        self.policy['max_events_per_day'] = 1
        self.runner.run(self.policy, apply=True)
        other = DailyRunner(self.api, self.settings, self.temp.name, today=lambda: self.date)
        self.assertEqual(other.run(self.policy, apply=True), {})
        self.assertEqual(self.api.writes, ['301'])
        self.date = '2026-11-10'
        other.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, ['301', '302'])

    def test_100_attempts_max_with_101_candidates(self):
        template = copy.deepcopy(self.api.rows[0])
        self.api.rows = [dict(template, eventid=str(1000 + i)) for i in range(101)]
        result = self.runner.run(self.policy, apply=True)
        self.assertEqual(len(result), 100)
        self.assertEqual(len(self.api.writes), 100)
        self.assertEqual(self.runner.run(self.policy, apply=True), {})

    def test_unknown_outcome_is_not_retried_even_next_day(self):
        self.api.fail_write = True
        self.runner.run(self.policy, apply=True)
        self.date = '2026-11-10'
        self.assertEqual(self.runner.run(self.policy, apply=True), {})
        self.assertEqual(len(self.api.writes), 2)

    def test_ip_secondary_ipv6_and_no_match(self):
        self.policy['rules'][0]['include_ips'] = ['2001:db8::/64']
        self.assertEqual(set(self.runner.run(self.policy)), {'301'})
        self.policy['rules'][0]['include_ips'] = ['192.0.2.99']
        self.assertEqual(self.runner.run(self.policy), {})

    def test_dns_host_included_without_ip_filter(self):
        self.assertIn('302', self.runner.run(self.policy))

    def test_exact_case_insensitive_group_name(self):
        rule = self.policy['rules'][0]
        del rule['groupid']
        rule['group_name'] = 'BANCO ESTADO (demo)'
        self.assertEqual(len(self.runner.run(self.policy)), 2)
        rule['group_name'] = 'Banco'
        with self.assertRaises(ValueError):
            self.runner.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, [])

    def test_ambiguous_group_name_rejected(self):
        rule = self.policy['rules'][0]
        del rule['groupid']
        rule['group_name'] = 'Banco estado (DEMO)'
        self.api.groups.append({'groupid': '999', 'name': 'BANCO ESTADO (demo)'})
        with self.assertRaises(ValueError):
            self.runner.run(self.policy, apply=True)

    def test_invalid_scope_fails_before_any_write(self):
        self.policy['rules'].append(dict(self.policy['rules'][0], groupid='999'))
        with self.assertRaises(ValueError):
            self.runner.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, [])

    def test_disabled_policy_or_dry_run_blocks_apply(self):
        for field in ('enabled', 'permissions_verified'):
            with self.subTest(field=field):
                policy = copy.deepcopy(self.policy)
                policy[field] = False
                with self.assertRaises(ValueError):
                    self.runner.run(policy, apply=True)
        self.settings.dry_run = True
        with self.assertRaises(ValueError):
            self.runner.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, [])

    def test_bad_policy_values_rejected(self):
        for field, value in [('daily_at', '24:01'), ('max_events_per_day', 0), ('max_events_per_day', True)]:
            bad = dict(self.policy, **{field: value})
            with self.assertRaises(ValueError):
                validate_policy(bad)
        self.policy['rules'][0]['include_ips'] = ['invalid-ip']
        with self.assertRaises(ValueError):
            validate_policy(self.policy)

    def test_state_write_failure_blocks_api_write(self):
        with patch.object(self.runner, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.runner.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, [])

    def test_crash_reservation_already_on_disk_before_network(self):
        original = self.api.suppress

        def check(eid, **kwargs):
            ledger = json.loads((Path(self.temp.name) / 'daily_state.json').read_text())
            self.assertIn(eid, ledger['events'])
            self.assertGreater(ledger['days'][self.date], 0)
            return original(eid, **kwargs)

        self.api.suppress = check
        self.runner.run(self.policy, apply=True)

    def test_overlapping_execution_blocked(self):
        with process_lock(Path(self.temp.name) / 'daily.lock'):
            with self.assertRaises(ValueError):
                self.runner.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, [])

    def test_malformed_ledger_blocks_writes(self):
        (Path(self.temp.name) / 'daily_state.json').write_text('[]')
        with self.assertRaises(ValueError):
            self.runner.run(self.policy, apply=True)
        self.assertEqual(self.api.writes, [])

    def test_missing_comment_not_reported_as_verified(self):
        original = self.api.suppress

        def strip_comment(eid, **kwargs):
            result = original(eid, **kwargs)
            next(row for row in self.api.rows if row['eventid'] == eid)['acknowledges'] = []
            return result

        self.api.suppress = strip_comment
        result = self.runner.run(self.policy, apply=True)
        self.assertTrue(all('NO VERIFICADO' in r for r in result.values()))
