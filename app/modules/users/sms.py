import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SmsSender(Protocol):
    async def send(self, phone: str, text: str) -> None: ...


class LoggingSmsSender:
    """Stub until a real SMS provider is connected."""

    async def send(self, phone: str, text: str) -> None:
        logger.info("SMS to %s: %s", phone, text)


def get_sms_sender() -> SmsSender:
    return LoggingSmsSender()
