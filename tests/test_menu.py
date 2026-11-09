import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cli.tables import export_csv
from config.settings import ROOT
from main import main
from server.alertas.controllers import AlertController
from server.alertas.managers import AlertManager
from server.alertas.views.terminal import TerminalView
from tests.helpers import fixture


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.settings, self.api, self.problems = fixture()
        self.output = []

    def controller(self, answers):
        iterator = iter(answers)
        view = TerminalView(lambda _: next(iterator), self.output.append)
        return AlertController(AlertManager(self.api, self.settings), view, self.settings)

    def test_demo_menu_complete_flow(self):
        controller = self.controller(['1', '', '1', '2', '3', '0', '3', '4', '5', 'todos', 'APLICAR', '0'])
        controller.run()
        self.assertEqual(self.api.writes, [])
        self.assertIn('SIMULACIÓN: sin escritura', '\n'.join(self.output))

    def test_change_group_invalidates_results(self):
        controller = self.controller(['', '2'])
        controller.state.hosts = self.api.hosts
        controller.state.problems = self.problems.fetch(self.api.hosts)
        controller.select_group()
        self.assertEqual(controller.state.hosts, [])
        self.assertEqual(controller.state.problems, [])

    def test_change_days_invalidates_results(self):
        controller = self.controller(['30'])
        controller.state.problems = self.problems.fetch(self.api.hosts)
        controller.change_days()
        self.assertEqual(self.settings.days, 30)
        self.assertEqual(controller.state.problems, [])

    def test_export_protects_formulas_and_overwrites(self):
        rows = self.problems.fetch(self.api.hosts)
        rows[0].name = '=HYPERLINK("bad")'
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            path = Path(directory) / 'report.csv'
            export_csv(path, rows, self.problems)
            self.assertIn("'=HYPERLINK", path.read_text(encoding='utf-8-sig'))
            with self.assertRaises(FileExistsError):
                export_csv(path, rows, self.problems)

    def test_demo_never_instantiates_real_client(self):
        with patch('main.ZabbixAPI') as real, patch('main.run'), patch('main.setup'), patch('server.alertas.web.serve'), patch('builtins.print'):
            self.assertEqual(main(['--demo']), 0)
            real.assert_not_called()

    def test_web_debug_uses_real_client_without_demo(self):
        with patch('main.Settings.load', return_value=self.settings), patch('main.ZabbixAPI') as real, \
                patch('main.DemoAPI') as demo, patch('main.setup'), patch('main.run') as terminal, \
                patch('server.alertas.web.serve') as serve, patch('builtins.print'):
            real.return_value.connect.return_value = '7.4.16'
            self.assertEqual(main(['--web', '--read-only', '--debug']), 0)
            real.assert_called_once()
            demo.assert_not_called()
            terminal.assert_not_called()
            serve.assert_called_once()
            self.assertFalse(serve.call_args.kwargs['demo'])
            self.assertTrue(serve.call_args.args[1].debug)
            self.assertTrue(serve.call_args.args[1].dry_run)

    def test_eof_exits(self):
        view = TerminalView(read=lambda _: (_ for _ in ()).throw(EOFError()), write=self.output.append)
        AlertController(AlertManager(self.api, self.settings), view, self.settings).run()
        self.assertIn('Salida', self.output[-1])
