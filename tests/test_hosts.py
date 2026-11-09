import unittest
from services.groups import Groups
from services.hosts import Hosts
from utils.validators import select_numbers
from tests.helpers import fixture


class HostTests(unittest.TestCase):
    def setUp(self):
        _, self.api, _ = fixture()
        self.service = Hosts(self.api)

    def test_unknown_group(self):
        groups = Groups(self.api)
        with self.assertRaises(ValueError):
            groups.select(groups.list(), 'No existe')
        self.assertEqual(groups.list('inexistente'), [])

    def test_group_by_id_and_number(self):
        groups = Groups(self.api)
        for value in ('1', '101', 'id:101'):
            self.assertEqual(groups.select(groups.list(), value)['groupid'], '101')

    def test_empty_group(self):
        self.assertEqual(self.service.list('102'), [])

    def test_no_ip_and_dns_hosts_retained(self):
        hosts = self.service.list('101')
        self.assertEqual(len(hosts), 3)
        self.assertEqual(hosts[1]['interfaces'][0]['dns'], 'f5.example.invalid')

    def test_one_and_multiple(self):
        self.assertEqual(len(select_numbers('1', self.api.hosts)), 1)
        self.assertEqual(len(select_numbers('1,2,1', self.api.hosts)), 2)
        self.assertEqual(len(select_numbers('todos', self.api.hosts)), 3)

    def test_ip_cidr_and_secondary_ipv6(self):
        for text in ('192.0.2.10', '192.0.2.0/24', '2001:db8::10', '2001:db8::/64', '192.0.2.99,192.0.2.10'):
            self.assertEqual(len(self.service.filter_ips(self.api.hosts, text)), 1)

    def test_exclude_ips(self):
        self.assertEqual(len(self.service.filter_ips(self.api.hosts, '192.0.2.10', exclude=True)), 2)

    def test_invalid_ip_and_selection(self):
        with self.assertRaises(ValueError):
            self.service.filter_ips(self.api.hosts, '999.1.1.1')
        for text in ('0', '-1', '4', 'bad'):
            with self.assertRaises(ValueError):
                select_numbers(text, self.api.hosts)
