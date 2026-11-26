import pytest

from app.phone import normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "+993 65 12 34 56",
        "+99365123456",
        "99365123456",
        "865123456",
        "65123456",
        "+993 (65) 12-34-56",
    ],
)
def test_normalize(raw):
    assert normalize_phone(raw) == "+99365123456"


@pytest.mark.parametrize("raw", ["", "123", "+7 999 123 45 67", "abc"])
def test_reject(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)
