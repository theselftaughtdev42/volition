from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import BUSINESS
from volition import invoicing
from volition.core.app import create_app
from volition.core.models import Business
from volition.core.store import db
from volition.core.store.business import save_business
from volition.invoicing.models import Invoice, InvoicingSettings
from volition.invoicing.store.settings import save_settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def schema(isolated_dirs: Path) -> None:
    """Core's and invoicing's tables, as the app creates them at startup, for tests that use the store directly."""
    db.migrate([invoicing.module])


@pytest.fixture
def app() -> FastAPI:
    return create_app([invoicing.module])


@pytest.fixture
def invoice() -> Invoice:
    return Invoice.model_validate_json((FIXTURES / "invoice.json").read_text())


@pytest.fixture
def business() -> Business:
    """Saved, as it would be after the shell's first run."""
    save_business(BUSINESS)
    return BUSINESS


SETTINGS = InvoicingSettings.model_validate_json((FIXTURES / "settings.json").read_text())


@pytest.fixture
def settings() -> InvoicingSettings:
    """Saved, as they would be after invoicing's first run."""
    save_settings(SETTINGS)
    return SETTINGS


@pytest.fixture
def client(app: FastAPI, business: Business, settings: InvoicingSettings) -> Iterator[TestClient]:
    # The context manager runs the lifespan.
    with TestClient(app, base_url="http://localhost") as c:
        yield c
