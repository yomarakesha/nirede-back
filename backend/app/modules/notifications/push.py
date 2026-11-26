import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class PushSender(Protocol):
    async def send(
        self, tokens: list[str], title: str, body: str, data: dict[str, Any]
    ) -> None: ...


class LoggingPushSender:
    """Stub until FCM is connected."""

    async def send(self, tokens: list[str], title: str, body: str, data: dict[str, Any]) -> None:
        logger.info("push to %d device(s): %s", len(tokens), title)


def get_push_sender() -> PushSender:
    return LoggingPushSender()


@dataclass
class PushMessage:
    tokens: list[str]
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


async def send_all(messages: list[PushMessage], push: PushSender) -> None:
    for m in messages:
        try:
            await push.send(m.tokens, m.title, m.body, m.data)
        except Exception:
            logger.exception("push delivery failed")
