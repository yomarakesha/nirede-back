import logging

from app.modules.users.sms import LoggingSmsSender


async def test_stub_does_not_log_code_by_default(caplog):
    caplog.set_level(logging.INFO)
    await LoggingSmsSender(debug=False).send("+99365123456", "Nirede: 1234")
    assert "1234" not in caplog.text
    assert "+99365123456" not in caplog.text


async def test_stub_logs_code_in_debug(caplog):
    caplog.set_level(logging.INFO)
    await LoggingSmsSender(debug=True).send("+99365123456", "Nirede: 1234")
    assert "1234" in caplog.text
