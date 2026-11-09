import logging
from datetime import datetime
from config.settings import ROOT
from cli.tables import export_csv
from server.alertas.models import Selection
from services.zabbix_api import APIError
from utils.logger import LOG_PATH
from utils.validators import select_numbers

log = logging.getLogger('zabbix')


class AlertController:
    def __init__(self, manager, view, settings):
        self.manager, self.view, self.settings = manager, view, settings
        self.state = Selection()

    def run(self):
        actions = {'1': self.select_group, '2': self.select_hosts, '3': self.query,
                   '4': self.show_eligible, '5': self.suppress, '6': self.export,
                   '7': self.show_logs, '8': self.change_days}
        while True:
            try:
                self.view.menu(self.state, self.settings)
                choice = self.view.ask('Opción: ')
                if choice == '0':
                    return
                if choice not in actions:
                    raise ValueError('Opción inválida.')
                actions[choice]()
            except (ValueError, APIError, OSError) as exc:
                log.warning('%s', exc)
                self.view.show('ERROR: ' + str(exc))
            except (EOFError, KeyboardInterrupt):
                self.view.show('Salida; no se realizan nuevas operaciones.')
                return

    def select_group(self):
        term = self.view.ask('Buscar grupo (vacío=todos; 0=volver; ejemplo: %s): ' % self.settings.group)
        if term == '0':
            return
        groups = self.manager.groups.list(term)
        if not groups:
            self.view.show('No se encontraron grupos visibles.')
            return
        self.view.groups(groups)
        choice = self.view.ask('Número o id:GROUPID (0=volver): ')
        if choice == '0':
            return
        group = self.manager.groups.select(groups, choice)
        self.state = Selection(group=group)
        log.info('Grupo seleccionado=%s groupid=%s', group['name'], group['groupid'])

    def select_hosts(self):
        if not self.state.group:
            raise ValueError('Seleccione primero un grupo.')
        hosts = self.manager.hosts.list(self.state.group['groupid'])
        if not hosts:
            self.state.hosts, self.state.problems = [], []
            self.view.show('Grupo sin equipos visibles.')
            return
        while True:
            self.view.hosts(hosts)
            self.view.show('Selección actual: ' + ', '.join(h['host'] for h in self.state.hosts))
            self.view.show('1=uno; 2=varios; 3=todos; 4=IP exacta; 5=varias IP; 6=CIDR; 7=excluir; 0=volver')
            option = self.view.ask('Selección de equipos: ')
            if option == '0':
                return
            if option in ('1', '2'):
                text = self.view.ask('Número(s) separados por comas (0=volver): ')
                if text == '0':
                    continue
                chosen = select_numbers(text, hosts)
                if option == '1' and len(chosen) != 1:
                    raise ValueError('Seleccione un único equipo.')
            elif option == '3':
                chosen = list(hosts)
            elif option in ('4', '5', '6'):
                text = self.view.ask('IP(s) o CIDR (0=volver): ')
                if text == '0':
                    continue
                if option in ('4', '5') and '/' in text:
                    raise ValueError('Para redes use la opción CIDR.')
                if option == '4' and ',' in text:
                    raise ValueError('Ingrese una única IP.')
                chosen = self.manager.hosts.filter_ips(hosts, text)
            elif option == '7':
                self.view.hosts(self.state.hosts)
                text = self.view.ask('Excluir números de selección actual o ip:IP[,IP/CIDR] (0=volver): ')
                if text == '0':
                    continue
                if text.startswith('ip:'):
                    chosen = self.manager.hosts.filter_ips(self.state.hosts, text[3:], exclude=True)
                else:
                    excluded = {h['hostid'] for h in select_numbers(text, self.state.hosts)}
                    chosen = [h for h in self.state.hosts if h['hostid'] not in excluded]
            else:
                raise ValueError('Opción inválida.')
            self.state.hosts, self.state.problems = chosen, []
            log.info('Hosts seleccionados=%s', [h['hostid'] for h in chosen])
            self.view.show('Equipos seleccionados: %d' % len(chosen))

    def query(self):
        if not self.state.hosts:
            raise ValueError('Seleccione al menos un equipo.')
        self.state.problems = []  # Never keep a successful but stale result after a failed refresh.
        self.state.problems = self.manager.problems.fetch(self.state.hosts)
        log.info('Filtros días>%d severity=%d patrones=%s etiquetas=%s', self.settings.days, self.settings.severity,
                 self.settings.patterns, self.settings.tags)
        self.view.show('Problemas abiertos consultados: %d' % len(self.state.problems))
        self.view.problems(self.manager.problems.eligible(self.state.problems), self.manager.problems)

    def show_eligible(self):
        self.view.problems(self.manager.problems.eligible(self.state.problems), self.manager.problems)

    def suppress(self):
        eligible = self.manager.problems.eligible(self.state.problems)
        if not eligible:
            raise ValueError('No hay eventos elegibles; consulte primero las alertas.')
        self.view.problems(eligible, self.manager.problems)
        text = self.view.ask('Eventos: número(s), todos o 0=volver: ')
        if text == '0':
            return
        selected = select_numbers(text, eligible)
        self.view.show('LISTA EXACTA A CONFIRMAR:')
        self.view.show('Mensaje que se registrará en Zabbix: ' + self.manager.suppression.message())
        self.view.problems(selected, self.manager.problems)
        self.view.show('ADVERTENCIA: la supresión puede afectar visibilidad, escalaciones y notificaciones de estos eventos, incluso InvGate.')
        self.view.show('El evento permanecerá abierto hasta su recuperación real. Modo: ' +
                       ('SIMULACIÓN' if self.settings.dry_run else 'REAL'))
        permissions = False
        if not self.settings.dry_run:
            self.view.show('Verifique con el administrador que el token puede acceder a los eventos, usar event.acknowledge y suprimir problemas. No existe una comprobación sin escritura que garantice todos esos permisos.')
            permissions = self.view.ask('Escriba PERMISOS VERIFICADOS si ya se comprobaron en Zabbix: ') == 'PERMISOS VERIFICADOS'
        confirmation = self.view.ask('Escriba APLICAR para confirmar (otro texto cancela): ')
        results = self.manager.suppression.apply(selected, self.state.hosts, confirmation, permissions)
        for eventid, result in results.items():
            self.view.show('Evento %s: %s' % (eventid, result))
        if not self.settings.dry_run:
            self.state.problems = []
            self.view.show('Consulte nuevamente para actualizar resultados.')

    def export(self):
        if not self.state.problems:
            raise ValueError('No hay resultados; consulte primero las alertas.')
        choice = self.view.ask('Exportar 1=elegibles, 2=todos los consultados, 0=volver: ')
        if choice == '0':
            return
        if choice not in ('1', '2'):
            raise ValueError('Opción inválida.')
        directory = ROOT / 'exports'
        directory.mkdir(exist_ok=True)
        path = directory / ('alertas_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv')
        rows = self.state.problems if choice == '2' else self.manager.problems.eligible(self.state.problems)
        self.view.show('CSV: ' + str(export_csv(path, rows, self.manager.problems)))

    def show_logs(self):
        if LOG_PATH.exists():
            for line in LOG_PATH.read_text(encoding='utf-8').splitlines()[-80:]:
                self.view.show(line)
        else:
            self.view.show('Sin logs disponibles.')

    def change_days(self):
        text = self.view.ask('Días: 7, 14, 30 o entero positivo (0=volver): ')
        if text == '0':
            return
        days = int(text)
        if days < 1:
            raise ValueError('Los días deben ser positivos.')
        self.settings.days = days
        self.state.problems = []
        log.info('Antigüedad cambiada a >%d días; resultados invalidados', days)
