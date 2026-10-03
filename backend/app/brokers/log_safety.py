"""Redact broker account paths from httpx's optional INFO request logging."""
import logging
import re


class BrokerAccountFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        sanitized = re.sub(r'(https://(?:demo|live)\.tradelocker\.com/backend-api/trade/accounts/)[^/?\s]+',
                           r'\1[account]', message)
        if sanitized != message:
            record.msg, record.args = sanitized, ()
        return True


def protect_broker_http_logs():
    logger = logging.getLogger('httpx')
    if not any(isinstance(item, BrokerAccountFilter) for item in logger.filters):
        logger.addFilter(BrokerAccountFilter())
