import csv
import time
from pathlib import Path


def safe_text(value):
    return ''.join(c if c.isprintable() else ' ' for c in str(value))


def table(headers, rows, write=print):
    rows = [[safe_text(v) for v in row] for row in rows]
    widths = [max([len(h)] + [len(row[i]) for row in rows]) for i, h in enumerate(headers)]
    write(' | '.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    write('-+-'.join('-' * w for w in widths))
    for row in rows:
        write(' | '.join(v.ljust(widths[i]) for i, v in enumerate(row)))


def problem_rows(problems, manager):
    now = time.time()
    return [[i, p.eventid, ', '.join(h['host'] for h in p.hosts), p.name,
             p.started, '%.2f' % p.age(now), p.severity, 'Sí' if p.acknowledged else 'No',
             'Sí' if p.suppressed else 'No', manager.reason(p, now) or 'Elegible']
            for i, p in enumerate(problems, 1)]


HEADERS = ['Nº', 'Event ID', 'Host', 'Problema / Pool / VS completo', 'Inicio UTC',
           'Días', 'Severidad', 'Reconocido', 'Suprimido', 'Evaluación']


def export_csv(path, problems, manager):
    path = Path(path)
    # Refuse overwrites; neutralize spreadsheet formula injection in remote names.
    def cell(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows([[cell(v) for v in row] for row in problem_rows(problems, manager)])
    return path.resolve()
