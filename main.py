#!/usr/bin/env python3
import argparse
import os
from cli.menu import run
from config.settings import Settings
from services.demo import DemoAPI
from services.zabbix_api import APIError, ZabbixAPI
from utils.logger import setup


def main(argv=None):
    parser = argparse.ArgumentParser(description='Gestión manual de alertas F5 por API Zabbix 7.4')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--demo', action='store_true', help='Datos ficticios, cero conexiones')
    parser.add_argument('--env', help='Archivo env protegido alternativo')
    parser.add_argument('--check', action='store_true', help='Validar conexión de lectura y salir')
    parser.add_argument('--read-only', action='store_true', help='Forzar simulación aunque DRY_RUN=false')
    parser.add_argument('--web', action='store_true', help='Abrir servidor web local para el navegador')
    parser.add_argument('--port', type=int, default=8080, help='Puerto web local (8080 por defecto)')
    args = parser.parse_args(argv)
    if os.name == 'posix':
        os.umask(0o077)
    try:
        settings = Settings() if args.demo else Settings.load(args.env)
        settings.debug = settings.debug or args.debug
        settings.dry_run = settings.dry_run or args.read_only or args.demo
        logger = setup(settings.debug, settings.token)
        api = DemoAPI() if args.demo else ZabbixAPI(settings)
        version = api.connect()
        print('[OK] Conexión establecida' if not args.demo else '[DEMO] Datos ficticios; sin conexión real')
        print('[OK] API Zabbix disponible: ' + version)
        logger.info('Inicio versión=%s simulación=%s', version, settings.dry_run)
        if not args.check:
            if args.web:
                from server.alertas.web import serve
                serve(api, settings, version, demo=args.demo, port=args.port)
            else:
                run(api, settings)
        return 0
    except (APIError, ValueError, OSError) as exc:
        # Settings may not be loaded yet; do not dump environment or traceback.
        print('ERROR: ' + str(exc))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
