import pytest

from app.modules.users import service
from app.modules.users.sms import get_sms_sender


class FakeSms:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, text: str) -> None:
        self.sent.append((phone, text))


@pytest.fixture
def sms(app, monkeypatch):
    fake = FakeSms()
    app.dependency_overrides[get_sms_sender] = lambda: fake
    monkeypatch.setattr(service, "generate_otp", lambda: "1234")
    return fake
