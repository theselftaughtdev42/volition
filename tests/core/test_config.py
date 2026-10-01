from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from volition.core.config import allowed_hosts, timezone


@pytest.mark.parametrize(
    ("env", "hosts"),
    [
        (None, ["127.0.0.1", "localhost", "[::1]"]),
        ("", ["127.0.0.1", "localhost", "[::1]"]),
        (" Invoices.example.com , localhost,", ["invoices.example.com", "localhost"]),
        ("*", ["*"]),
    ],
)
def test_allowed_hosts_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, env: str | None, hosts: list[str]
) -> None:
    if env is None:
        monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_HOSTS", env)
    assert allowed_hosts() == hosts


@pytest.mark.parametrize(("env", "zone"), [(None, "Europe/London"), ("", "Europe/London"), ("UTC", "UTC")])
def test_timezone_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch, env: str | None, zone: str) -> None:
    if env is None:
        monkeypatch.delenv("TIMEZONE", raising=False)
    else:
        monkeypatch.setenv("TIMEZONE", env)
    assert timezone() == ZoneInfo(zone)


def test_an_unknown_timezone_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus_Mons")
    with pytest.raises(ZoneInfoNotFoundError):
        timezone()
