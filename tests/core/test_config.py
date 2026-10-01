import pytest

from volition.core.config import allowed_hosts


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
