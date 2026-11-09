"""Small allow-listed JSON-RPC client. Never retries writes or follows redirects."""
import json
import logging
import socket
import ssl
import urllib.error
import urllib.request

log = logging.getLogger('zabbix')


class APIError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ZabbixAPI:
    READ_METHODS = {'apiinfo.version', 'hostgroup.get', 'host.get', 'problem.get'}

    def __init__(self, settings, opener=None):
        self.settings = settings
        self.counter = 0
        context = ssl.create_default_context(cafile=settings.ca_file or None)
        self.opener = opener or urllib.request.build_opener(
            NoRedirect(), urllib.request.HTTPSHandler(context=context))

    def call(self, method, params):
        if method not in self.READ_METHODS:
            raise APIError('Método de lectura no autorizado.')
        return self._request(method, params)

    def suppress(self, eventid, *, confirmation, permissions_confirmed, message=None):
        if self.settings.dry_run or confirmation != 'APLICAR' or not permissions_confirmed:
            raise APIError('Escritura bloqueada por las condiciones de seguridad.')
        message = self.settings.suppression_message if message is None else message
        if not isinstance(message, str) or not message.strip() or len(message) > 2048:
            raise APIError('Mensaje de supresión vacío o demasiado largo.')
        return self._request('event.acknowledge', {
            'eventids': [str(eventid)], 'action': 36, 'suppress_until': 0, 'message': message})

    def _request(self, method, params):
        self.counter += 1
        request_id = self.counter
        log.debug('API método=%s parámetros=%s', method, params)
        headers = {'Content-Type': 'application/json-rpc'}
        if method != 'apiinfo.version':
            headers['Authorization'] = 'Bearer ' + self.settings.token
        request = urllib.request.Request(self.settings.url, data=json.dumps({
            'jsonrpc': '2.0', 'method': method, 'params': params, 'id': request_id
        }).encode(), headers=headers, method='POST')
        try:
            with self.opener.open(request, timeout=self.settings.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise APIError('HTTP %s: revise autenticación/permisos y endpoint; no se siguen redirecciones.' % exc.code) from None
        except (ssl.SSLError, urllib.error.URLError) as exc:
            reason = getattr(exc, 'reason', exc)
            if isinstance(reason, ssl.SSLError):
                message = 'Error TLS: revise certificado y ZBX_CA_FILE; validación SSL obligatoria.'
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                message = 'Tiempo de espera agotado; compruebe conectividad.'
            else:
                message = 'No se pudo conectar; revise DNS, red y endpoint HTTPS.'
            raise APIError(message) from None
        except (TimeoutError, socket.timeout):
            raise APIError('Tiempo de espera agotado; no se reintenta la operación.') from None
        except (ValueError, UnicodeError):
            raise APIError('Respuesta JSON inválida del servidor.') from None
        if not isinstance(data, dict) or data.get('id') != request_id or data.get('jsonrpc') != '2.0':
            raise APIError('Respuesta JSON-RPC inválida o ID inesperado.')
        if 'error' in data:
            # Do not echo remote content: it may contain credentials or HTML.
            raise APIError('La API rechazó %s: revise token, permisos y parámetros (detalle remoto omitido).' % method)
        if 'result' not in data:
            raise APIError('La API no devolvió result.')
        return data['result']

    def connect(self):
        if not self.settings.token or self.settings.token == 'REEMPLAZAR':
            raise APIError('Configure ZBX_API_TOKEN en el entorno o config.env protegido.')
        version = self.call('apiinfo.version', {})
        if not isinstance(version, str) or not version.startswith('7.4.'):
            raise APIError('Se requiere API Zabbix 7.4.x.')
        self.call('hostgroup.get', {'output': ['groupid', 'name']})
        log.info('API versión=%s; lectura autenticada validada', version)
        return version
