import logging
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)


class SmsSender(Protocol):
    async def send(self, phone: str, text: str) -> None: ...


class LoggingSmsSender:
    """Stub until a real SMS provider is connected.

    Logs the message body (and so the OTP) only when `debug` is on, for local development.
    """

    def __init__(self, debug: bool) -> None:
        self.debug = debug

    async def send(self, phone: str, text: str) -> None:
        if self.debug:
            logger.info("SMS to %s: %s", phone, text)
        else:
            logger.info("SMS to ***%s (body hidden)", phone[-2:])


def get_sms_sender() -> SmsSender:
    return LoggingSmsSender(debug=get_settings().sms_debug_log)
