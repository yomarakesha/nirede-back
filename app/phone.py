import re

_ALLOWED = re.compile(r"^\+?[\d\s()\-]+$")


def normalize_phone(raw: str) -> str:
    """Normalize a Turkmenistan phone number to E.164 `+993XXXXXXXX`."""
    if not raw or not _ALLOWED.match(raw.strip()):
        raise ValueError("invalid_phone")
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("993"):
        local = digits[3:]
    elif len(digits) == 9 and digits.startswith("8"):
        local = digits[1:]
    elif len(digits) == 8 and not raw.strip().startswith("+"):
        local = digits
    else:
        raise ValueError("invalid_phone")
    return f"+993{local}"
