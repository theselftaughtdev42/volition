from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import BUSINESS
from volition import subscriptions
from volition.core.app import create_app
from volition.core.store import db
from volition.core.store.business import save_business
from volition.subscriptions import renewals

#: What "today" is in every test here.
TODAY = date(2026, 11, 27)


@pytest.fixture(autouse=True)
def schema(isolated_dirs: Path) -> None:
    """Core's and the module's tables, as the app creates them at startup, for tests that use the store directly."""
    db.migrate([subscriptions.module])


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr(renewals, "today", lambda: TODAY)
    return TODAY


@pytest.fixture
def app() -> FastAPI:
    return create_app([subscriptions.module])


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://localhost") as c:
        save_business(BUSINESS)
        yield c
