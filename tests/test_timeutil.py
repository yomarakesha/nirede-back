from datetime import UTC, datetime, time

from app.timeutil import is_open


def _local(h, m=0):  # Asia/Ashgabat is UTC+5
    return datetime(2026, 11, 23, (h - 5) % 24, m, tzinfo=UTC)


def test_open_during_day():
    assert is_open(time(10), time(22), _local(12))


def test_closed_after_close():
    assert not is_open(time(10), time(22), _local(22, 30))


def test_overnight_open_after_midnight():
    assert is_open(time(10), time(2), _local(1))


def test_overnight_closed_morning():
    assert not is_open(time(10), time(2), _local(9))


def test_missing_hours_closed():
    assert not is_open(None, None, _local(12))
