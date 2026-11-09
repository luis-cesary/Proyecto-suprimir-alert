from cli.tables import HEADERS, problem_rows, safe_text, table
from config.settings import SEVERITIES


class TerminalView:
    def __init__(self, read=input, write=print):
        self.read, self.write = read, write

    def ask(self, text):
        return self.read(text).strip()

    def show(self, text):
        self.write(safe_text(text))

    def menu(self, state, settings):
        self.write('\n' + '=' * 60)
        self.show('ZABBIX 7.4.16 - GESTIÓN DE ALERTAS ANTIGUAS')
        self.show('GRUPO: %s | EQUIPOS: %d | >%d días | %s | %s' % (
            state.group.get('name', 'Sin seleccionar'), len(state.hosts), settings.days, SEVERITIES[settings.severity],
            'SIMULACIÓN' if settings.dry_run else 'ESCRITURA MANUAL HABILITADA'))
        self.write('1. Seleccionar grupo de hosts\n2. Seleccionar equipos\n3. Consultar alertas\n'
                   '4. Ver alertas elegibles para supresión\n5. Suprimir alertas seleccionadas\n'
                   '6. Exportar resultados CSV\n7. Ver logs de depuración\n'
                   '8. Cambiar antigüedad (7, 14, 30 o personalizada)\n0. Salir')

    def groups(self, rows):
        table(['Nº', 'Group ID', 'Grupo'], [[i, g['groupid'], g['name']]
              for i, g in enumerate(rows, 1)], self.write)

    def hosts(self, rows):
        table(['Nº', 'Host ID', 'Hostname', 'Nombre visible', 'Interfaces IP/DNS', 'Estado'],
              [[i, h['hostid'], h['host'], h['name'],
                ', '.join('%s%s' % (it.get('ip', '') or 'sin IP',
                                     (' DNS:' + it.get('dns', '')) if it.get('useip') == '0' else '')
                          for it in h.get('interfaces', [])) or 'sin interfaces',
                'Habilitado' if h['status'] == '0' else 'Deshabilitado']
               for i, h in enumerate(rows, 1)], self.write)

    def problems(self, problems, manager):
        table(HEADERS, problem_rows(problems, manager), self.write)
        self.show('Total mostrado: %d | Elegibles: %d' % (len(problems), len(manager.eligible(problems))))
