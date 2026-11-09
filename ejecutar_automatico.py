#!/usr/bin/env python3
"""Una pasada real sin interacción ni parámetros; lee todo desde config.env."""
from run_daily import main


def run():
    return main(['--apply'])


if __name__ == '__main__':
    raise SystemExit(run())
