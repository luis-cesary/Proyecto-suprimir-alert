import ipaddress


def select_numbers(text, rows):
    if text.strip().lower() == 'todos':
        return list(rows)
    try:
        indexes = list(dict.fromkeys(int(x.strip()) for x in text.split(',')))
    except ValueError:
        raise ValueError('Use números separados por comas o todos.') from None
    if not indexes or any(i < 1 or i > len(rows) for i in indexes):
        raise ValueError('Selección fuera de rango.')
    return [rows[i - 1] for i in indexes]


def ip_networks(text):
    try:
        return [ipaddress.ip_network(x.strip(), strict=False) for x in text.split(',')]
    except ValueError:
        raise ValueError('IP o subred CIDR inválida.') from None


def matches_ips(host, networks):
    for interface in host.get('interfaces', []):
        try:
            ip = ipaddress.ip_address(interface.get('ip', ''))
        except ValueError:
            continue
        if any(ip.version == net.version and ip in net for net in networks):
            return True
    return False
