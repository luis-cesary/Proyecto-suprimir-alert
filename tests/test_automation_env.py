import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import ROOT
from config.automation import load_policy
from ejecutar_automatico import run


class AutomationEnvTests(unittest.TestCase):
    def load(self, text='', environment=None, apply=False):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            path = Path(directory) / 'config.env'
            path.write_text(text, encoding='utf-8')
            path.chmod(0o600)
            with patch.dict(os.environ, environment or {}, clear=True):
                return load_policy(path, apply=apply)

    def test_empty_env_never_enables_writes(self):
        self.assertFalse(self.load()['enabled'])
        with self.assertRaises(ValueError):
            self.load(apply=True)

    def test_all_settings_come_from_env(self):
        policy = self.load('AUTO_ENABLED=true\nAUTO_PERMISSIONS_VERIFIED=true\nAUTO_APPROVAL_REFERENCE=Prueba\n'
                           'AUTO_GROUP_NAME=Cliente\nAUTO_DAYS=30\nAUTO_MIN_SEVERITY=5\n'
                           'AUTO_INCLUDE_IPS=192.0.2.1, 2001:db8::/64\nAUTO_MAX_EVENTS_PER_DAY=20\nAUTO_DAILY_AT=01:10', apply=True)
        self.assertEqual(policy['daily_at'], '01:10')
        self.assertEqual(policy['max_events_per_day'], 20)
        rule = policy['rules'][0]
        self.assertEqual(rule['group_name'], 'Cliente')
        self.assertEqual(rule['min_severity'], 5)
        self.assertEqual(rule['days'], 30)
        self.assertEqual(rule['include_ips'], ['192.0.2.1', '2001:db8::/64'])
        self.assertTrue(rule['all_hosts_in_group'])

    def test_explicit_hosts_and_environment_override(self):
        policy = self.load('AUTO_HOST_IDS=201,202\nAUTO_MAX_EVENTS_PER_DAY=100', {'AUTO_MAX_EVENTS_PER_DAY': '5'})
        self.assertFalse(policy['rules'][0]['all_hosts_in_group'])
        self.assertEqual(policy['rules'][0]['hostids'], ['201', '202'])
        self.assertEqual(policy['max_events_per_day'], 5)

    def test_invalid_values_rejected(self):
        for text in ('AUTO_INCLUDE_IPS=bad', 'AUTO_INCLUDE_IPS=192.0.2.1,', 'AUTO_DAILY_AT=24:01',
                     'AUTO_MAX_EVENTS_PER_DAY=0', 'AUTO_MIN_SEVERITY=6'):
            with self.assertRaises(ValueError):
                self.load(text)

    def test_no_argument_entrypoint(self):
        with patch('ejecutar_automatico.main', return_value=0) as main:
            self.assertEqual(run(), 0)
            main.assert_called_once_with(['--apply'])
