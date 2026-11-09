from server.alertas.controllers import AlertController
from server.alertas.managers import AlertManager
from server.alertas.views.terminal import TerminalView


def run(api, settings):
    AlertController(AlertManager(api, settings), TerminalView(), settings).run()
