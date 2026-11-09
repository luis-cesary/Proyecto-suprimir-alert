"""Configuration without executing shell code or exposing secrets."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SEVERITIES = ('Sin clasificar', 'Información', 'Warning', 'Average', 'High', 'Disaster')


def boolean(value):
    if value.lower() not in ('true', 'false'):
        raise ValueError('Los booleanos deben ser true o false.')
    return value.lower() == 'true'


def read_values(path=None):
    path = Path(path) if path else ROOT / 'config.env'
    values = {}
    if path.exists():
        if os.name == 'posix' and path.stat().st_mode & 0o077:
            raise ValueError('config.env debe tener permisos 600 o 400.')
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep:
                raise ValueError('Línea env inválida; se espera CLAVE=valor.')
            values[key.strip()] = value.strip().strip('\"\'')
    values.update(os.environ)
    return values


@dataclass
class Settings:
    url: str = 'https://sim.itqlatam.com/api_jsonrpc.php'
    token: str = field(default='', repr=False)
    group: str = 'Banco estado'
    days: int = 14
    severity: int = 4
    severity_at_least: bool = False
    dry_run: bool = True
    max_write_events: int = 1
    debug: bool = False
    ca_file: str = ''
    timeout: int = 30
    suppression_message: str = 'Suprimido por superar el tiempo de espera aprobado con el cliente.'
    patterns: tuple = (r'(?i)\bF5\b.*\b(pool|virtual server|VS)\b',)
    tags: tuple = (('vendor', 'F5'),)
    resource_pattern: str = r'(?i)\b(pool|virtual server|VS)\b'

    @classmethod
    def load(cls, path=None):
        values = read_values(path)
        get = values.get
        tags = []
        for item in get('F5_TAGS', 'vendor=F5').split(';'):
            if item:
                key, sep, value = item.partition('=')
                if not sep or not key or not value:
                    raise ValueError('F5_TAGS requiere etiqueta=valor separados por ;')
                tags.append((key, value))
        result = cls(
            url=get('ZBX_API_URL', cls.url), token=get('ZBX_API_TOKEN', ''),
            group=get('DEFAULT_GROUP', 'Banco estado'), days=int(get('DEFAULT_DAYS', '14')),
            severity=int(get('DEFAULT_SEVERITY', '4')), dry_run=boolean(get('DRY_RUN', 'true')),
            max_write_events=int(get('MAX_WRITE_EVENTS', '1')), debug=boolean(get('DEBUG', 'false')),
            ca_file=get('ZBX_CA_FILE', ''), timeout=int(get('ZBX_TIMEOUT', '30')),
            suppression_message=get('SUPPRESSION_MESSAGE', cls.suppression_message),
            patterns=tuple(x for x in get('F5_NAME_PATTERNS', cls.patterns[0]).split(';;') if x),
            tags=tuple(tags), resource_pattern=get('F5_RESOURCE_PATTERN', cls.resource_pattern))
        parsed = urlsplit(result.url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('ZBX_API_URL debe ser HTTPS sin credenciales, query ni fragmento.')
        if result.days < 1 or result.max_write_events < 1 or result.timeout < 1:
            raise ValueError('Días, límite y timeout deben ser positivos.')
        if result.severity not in range(6):
            raise ValueError('DEFAULT_SEVERITY debe estar entre 0 y 5.')
        if not result.suppression_message.strip() or len(result.suppression_message) > 1500:
            raise ValueError('SUPPRESSION_MESSAGE debe tener entre 1 y 1500 caracteres.')
        for pattern in (*result.patterns, result.resource_pattern):
            re.compile(pattern)
        return result
