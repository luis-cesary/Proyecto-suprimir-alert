import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from config.settings import ROOT, Settings
from utils.logger import Redact


class SettingsTests(unittest.TestCase):
    def load(self, text, environment=None):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            path = Path(directory) / 'config.env'
            path.write_text(text, encoding='utf-8')
            path.chmod(0o600)
            with patch.dict(os.environ, environment or {}, clear=True):
                return Settings.load(path)

    def test_defaults_safe(self):
        settings = self.load('')
        self.assertTrue(settings.dry_run)
        self.assertEqual(settings.max_write_events, 1)

    def test_environment_precedence(self):
        settings = self.load('DEFAULT_DAYS=14', {'DEFAULT_DAYS': '30'})
        self.assertEqual(settings.days, 30)

    def test_unsafe_settings_rejected(self):
        for text in ('DRY_RUN=maybe', 'ZBX_API_URL=http://example.invalid', 'DEFAULT_DAYS=0',
                     'MAX_WRITE_EVENTS=0', 'DEFAULT_SEVERITY=6', 'ZBX_API_URL=https://user:pw@example.invalid'):
            with self.assertRaises(ValueError):
                self.load(text)

    def test_secret_not_in_repr_or_logs(self):
        self.assertNotIn('TOP_SECRET', repr(Settings(token='TOP_SECRET')))
        record = logging.LogRecord('zabbix', logging.INFO, '', 0, 'error %s', ('TOP_SECRET',), None)
        Redact('TOP_SECRET').filter(record)
        self.assertNotIn('TOP_SECRET', record.getMessage())
