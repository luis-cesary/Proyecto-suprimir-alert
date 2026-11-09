"""Arranque directo de la web con Zabbix real y logs, también desde PyCharm.

La supresión sigue controlada por DRY_RUN en config.env y confirmación manual.
No activa el modo demo ni incluye credenciales.
"""
from main import main


if __name__ == '__main__':
    raise SystemExit(main(['--web', '--debug']))
