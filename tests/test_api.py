import io
import json
import ssl
import unittest
import urllib.error
from unittest.mock import Mock
from config.settings import Settings
from services.zabbix_api import APIError, NoRedirect, ZabbixAPI


class APITests(unittest.TestCase):
    def setUp(self):
        self.opener = Mock()
        self.api = ZabbixAPI(Settings(token='secret-test'), self.opener)

    def response(self, result, request_id=1):
        return io.BytesIO(json.dumps({'jsonrpc': '2.0', 'id': request_id, 'result': result}).encode())

    def test_authenticated_connection(self):
        self.opener.open.side_effect = [self.response('7.4.16'), self.response([], 2)]
        self.assertEqual(self.api.connect(), '7.4.16')
        requests = self.opener.open.call_args_list
        self.assertIsNone(requests[0].args[0].get_header('Authorization'))
        self.assertEqual(requests[1].args[0].get_header('Authorization'), 'Bearer secret-test')

    def test_authentication_error_not_echoed(self):
        self.opener.open.return_value = io.BytesIO(json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'error': {'data': 'secret-test not authorized'}}).encode())
        with self.assertRaises(APIError) as caught:
            self.api.call('hostgroup.get', {})
        self.assertNotIn('secret-test', str(caught.exception))

    def test_only_allowed_methods(self):
        for method in ('event.acknowledge', 'trigger.update', 'user.get', 'script.execute'):
            with self.assertRaises(APIError):
                self.api.call(method, {})
        self.opener.open.assert_not_called()

    def test_write_guard(self):
        with self.assertRaises(APIError):
            self.api.suppress('1', confirmation='APLICAR', permissions_confirmed=True)
        self.opener.open.assert_not_called()

    def test_exact_suppression_payload(self):
        self.api.settings.dry_run = False
        self.opener.open.return_value = self.response({'eventids': ['301']})
        self.api.suppress('301', confirmation='APLICAR', permissions_confirmed=True)
        payload = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual(payload['params'], {'eventids': ['301'], 'action': 36, 'suppress_until': 0,
                                             'message': self.api.settings.suppression_message})
        self.assertEqual(payload['params']['action'] & (1 | 2 | 8 | 16), 0)

    def test_timeouts_never_retry(self):
        self.opener.open.side_effect = TimeoutError()
        with self.assertRaisesRegex(APIError, 'espera'):
            self.api.call('host.get', {})
        self.assertEqual(self.opener.open.call_count, 1)

    def test_tls_error(self):
        self.opener.open.side_effect = urllib.error.URLError(ssl.SSLError())
        with self.assertRaisesRegex(APIError, 'TLS'):
            self.api.call('host.get', {})

    def test_http_error(self):
        self.opener.open.side_effect = urllib.error.HTTPError('https://example.invalid', 403, '', {}, None)
        with self.assertRaisesRegex(APIError, '403'):
            self.api.call('host.get', {})

    def test_malformed_and_mismatched_response(self):
        for content in (b'not json', b'[]', b'{"id":99,"jsonrpc":"2.0","result":[]}'):
            self.opener.open.return_value = io.BytesIO(content)
            with self.assertRaises(APIError):
                self.api.call('host.get', {})

    def test_no_redirect(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def test_missing_token_no_network(self):
        self.api.settings.token = ''
        with self.assertRaises(APIError):
            self.api.connect()
        self.opener.open.assert_not_called()
