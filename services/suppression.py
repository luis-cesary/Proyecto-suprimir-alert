import logging
from services.zabbix_api import APIError

log = logging.getLogger('zabbix')


class Suppression:
    def __init__(self, api, problems, settings, before_write=None):
        self.api, self.problems, self.settings = api, problems, settings
        self.attempted = 0
        self.before_write = before_write

    def message(self):
        return '%s Plazo aplicado: %d días.' % (self.settings.suppression_message, self.problems.settings.days)

    def apply(self, selected, hosts, confirmation, permissions_confirmed=False):
        ids = list(dict.fromkeys(p.eventid for p in selected))
        log.info('Solicitud eventos=%s confirmación=%s simulación=%s', ids,
                 confirmation == 'APLICAR', self.settings.dry_run)
        if confirmation != 'APLICAR':
            return {i: 'CANCELADO: confirmación incorrecta' for i in ids}
        if self.settings.dry_run:
            return {i: 'SIMULACIÓN: sin escritura' for i in ids}
        if not permissions_confirmed:
            return {i: 'BLOQUEADO: falta confirmar permisos Zabbix' for i in ids}
        if len(ids) + self.attempted > self.settings.max_write_events:
            return {i: 'BLOQUEADO: límite de escrituras por sesión' for i in ids}
        result = {}
        for eventid in ids:
            try:
                fresh = self.problems.fetch(hosts, [eventid])
                current = next((p for p in fresh if p.eventid == eventid), None)
                reason = self.problems.reason(current) if current else 'recuperado, fuera de selección o sin acceso'
                if reason:
                    result[eventid] = 'OMITIDO: ' + reason
                else:
                    # Count attempts, including ambiguous network failures, to prevent retries.
                    self.attempted += 1
                    message = self.message()
                    if self.before_write:
                        self.before_write(eventid)
                    log.info('INTENTO supresión evento=%s action=36 suppress_until=0 mensaje=%s permisos confirmados', eventid, message)
                    reply = self.api.suppress(eventid, confirmation=confirmation,
                                              permissions_confirmed=permissions_confirmed, message=message)
                    if not isinstance(reply, dict) or [str(x) for x in reply.get('eventids', [])] != [eventid]:
                        raise APIError('Respuesta de escritura inesperada; verificar manualmente.')
                    after = self.problems.fetch(hosts, [eventid])
                    actual = next((p for p in after if p.eventid == eventid), None)
                    if actual and actual.suppressed:
                        if any(u.get('message') == message and int(u.get('action', 0)) & 4 for u in actual.updates):
                            result[eventid] = 'SUPRIMIDO: estado verificado; mensaje registrado'
                        else:
                            result[eventid] = 'NO VERIFICADO: suprimido, pero no se pudo verificar el mensaje; revisar historial'
                    else:
                        result[eventid] = 'NO VERIFICADO: pudo recuperarse o cambiar; revisar Monitoring → Problems'
            except APIError as exc:
                result[eventid] = 'FALLO / resultado no confirmado: ' + str(exc)
            log.info('Evento=%s resultado=%s', eventid, result[eventid])
        return result
