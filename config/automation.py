"""Daily policy from the same protected env as the Zabbix connection."""
from config.settings import boolean, read_values
from services.daily import validate_policy


def load_policy(path=None, apply=False):
    values = read_values(path)
    get = values.get
    ips = get('AUTO_INCLUDE_IPS', '').strip()
    hostids = get('AUTO_HOST_IDS', '').strip()
    policy = {
        'enabled': boolean(get('AUTO_ENABLED', 'false')),
        'permissions_verified': boolean(get('AUTO_PERMISSIONS_VERIFIED', 'false')),
        'approval_reference': get('AUTO_APPROVAL_REFERENCE', ''),
        'daily_at': get('AUTO_DAILY_AT', '00:01'),
        'max_events_per_day': int(get('AUTO_MAX_EVENTS_PER_DAY', '100')),
        'rules': [{
            'group_name': get('AUTO_GROUP_NAME', 'BANCO ESTADO'),
            'hostids': [h.strip() for h in hostids.split(',')] if hostids else [],
            'all_hosts_in_group': not bool(hostids),
            'include_ips': [ip.strip() for ip in ips.split(',')] if ips else [],
            'days': int(get('AUTO_DAYS', '14')),
            'min_severity': int(get('AUTO_MIN_SEVERITY', '4')),
        }],
    }
    return validate_policy(policy, apply=apply)
