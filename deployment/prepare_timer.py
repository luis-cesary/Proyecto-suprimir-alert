"""Generate reviewable systemd units. Does not install or enable anything."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.automation import load_policy


def main():
    parser = argparse.ArgumentParser(description='Generar timer desde la política aprobada, sin instalarlo')
    parser.parse_args()
    policy = load_policy(apply=True)
    directory = ROOT / 'deployment' / 'generated'
    directory.mkdir(exist_ok=True)
    target = '/opt/zabbix-automatizaciones/zabbix_f5_alert_manager'
    service = f'''[Unit]
Description=Supimir - supresion diaria de eventos aprobados
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=zbx-alertas
Group=zbx-alertas
WorkingDirectory={target}
ExecStart={target}/.venv/bin/python {target}/ejecutar_automatico.py
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={target}/runtime {target}/logs
TimeoutStartSec=1h
Restart=no
'''
    timer = f'''[Unit]
Description=Supimir - ejecucion diaria en horario de Chile

[Timer]
OnCalendar=*-*-* {policy['daily_at']}:00 America/Santiago
AccuracySec=1min
Persistent=false
Unit=zabbix-f5-daily.service

[Install]
WantedBy=timers.target
'''
    (directory / 'zabbix-f5-daily.service').write_text(service, encoding='utf-8')
    (directory / 'zabbix-f5-daily.timer').write_text(timer, encoding='utf-8')
    print('Unidades generadas en:', directory)
    print('Revise e instale en MonZabbix. No se habilitó ninguna tarea.')


if __name__ == '__main__':
    main()
