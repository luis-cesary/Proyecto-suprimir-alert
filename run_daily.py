#!/usr/bin/env python3
"""One invocation performs one bounded run and exits; systemd supplies the clock."""
import argparse
import json
import os
from dataclasses import replace
from pathlib import Path

from config.settings import ROOT, Settings
from config.automation import load_policy
from services.daily import DailyRunner, validate_policy
from services.zabbix_api import APIError, ZabbixAPI
from server.alertas.web import WebApp
from utils.logger import setup


def main(argv=None):
    parser = argparse.ArgumentParser(description='Ejecución diaria de alcance aprobado; por defecto solo plan')
    parser.add_argument('--policy', help='JSON alternativo; por defecto se usa config.env')
    parser.add_argument('--apply', action='store_true', help='Aplicar política previamente habilitada y aprobada')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args(argv)
    logger = None
    audit = None
    if os.name == 'posix':
        os.umask(0o077)
    try:
        policy = (validate_policy(json.loads(Path(args.policy).read_text(encoding='utf-8-sig')), args.apply)
                  if args.policy else load_policy(apply=args.apply))
        settings = Settings.load()
        if not args.apply:
            settings = replace(settings, dry_run=True)
        logger = setup(args.debug or settings.debug, settings.token)
        api = ZabbixAPI(settings)
        version = api.connect()
        # Reuse the web's persistent activity format without starting an HTTP server.
        audit = WebApp(api, settings, version).audit
        result = DailyRunner(api, settings, audit=audit).run(policy, args.apply)
        for eventid, outcome in result.items():
            print('Evento %s: %s' % (eventid, outcome))
        if not result:
            print('Sin eventos a procesar: no hay elegibles nuevos o se agotó el límite diario.')
        failed = any(value.startswith(('FALLO', 'NO VERIFICADO', 'BLOQUEADO')) for value in result.values())
        logger.info('Ejecución diaria finalizada: resultados=%d fallos=%s', len(result), failed)
        return 2 if failed else 0
    except (OSError, ValueError, APIError, KeyError) as exc:
        if logger:
            logger.error('Ejecución diaria fallida: %s', exc)
        if audit:
            try:
                audit(operation='AUTO ERROR', result=str(exc))
            except OSError:
                pass  # The original error remains visible in the journal/stdout.
        print('ERROR: ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
