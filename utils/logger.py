import logging
import os
from logging.handlers import RotatingFileHandler
from config.settings import ROOT

LOG_PATH = ROOT / 'logs' / 'zabbix_f5_debug.log'


class Redact(logging.Filter):
    def __init__(self, secret):
        super().__init__()
        self.secret = secret

    def filter(self, record):
        message = record.getMessage()
        if self.secret:
            message = message.replace(self.secret, '[REDACTADO]')
        record.msg, record.args = message, ()
        return True


def setup(debug=False, token=''):
    LOG_PATH.parent.mkdir(exist_ok=True)
    if os.name == 'posix':
        os.umask(0o077)
    logger = logging.getLogger('zabbix')
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=5, encoding='utf-8')
    if os.name == 'posix':
        LOG_PATH.chmod(0o600)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    handler.addFilter(Redact(token))
    logger.addHandler(handler)
    if debug:
        console = logging.StreamHandler()
        console.setFormatter(handler.formatter)
        console.addFilter(Redact(token))
        logger.addHandler(console)
    logger.propagate = False
    return logger
