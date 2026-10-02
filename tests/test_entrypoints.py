"""What the server runs: the composed app and `python -m volition`."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from volition import __main__


def test_the_composed_app_serves_invoicing() -> None:
    from volition.app import app

    with TestClient(app, base_url="http://localhost") as c:
        assert c.get("/health").status_code == 200
        res = c.get("/invoicing/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/business"


@pytest.mark.parametrize(
    ("env", "host", "port"),
    [({}, "127.0.0.1", 3000), ({"HOST": "0.0.0.0", "PORT": "8080"}, "0.0.0.0", 8080)],  # noqa: S104
)
def test_main_serves_the_app_on_host_and_port(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], host: str, port: int
) -> None:
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(__main__.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    __main__.main()
    assert calls == [(("volition.app:app",), {"host": host, "port": port})]
