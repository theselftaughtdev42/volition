from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from volition import invoicing
from volition.core.app import create_app
from volition.core.store import db
from volition.invoicing.models import Defaults, Invoice, PresetLineItem, Supplier
from volition.invoicing.store.defaults import save_defaults
from volition.invoicing.store.supplier import save_supplier

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def schema(isolated_dirs: Path) -> None:
    """Invoicing's tables, as the app creates them at startup, for tests that use the store directly."""
    db.migrate([invoicing.module])


@pytest.fixture
def app() -> FastAPI:
    return create_app([invoicing.module])


@pytest.fixture
def invoice() -> Invoice:
    return Invoice.model_validate_json((FIXTURES / "invoice.json").read_text())


SUPPLIER = Supplier.model_validate_json((FIXTURES / "supplier.json").read_text())


@pytest.fixture
def supplier() -> Supplier:
    """Saved, as it would be after the first run."""
    save_supplier(SUPPLIER)
    return SUPPLIER


DEFAULTS = Defaults(
    invoice_number_start=1,
    vat=True,
    unit="days",
    line_items=[PresetLineItem(description="IT & Software Consultancy Services", rate=650)],
)


@pytest.fixture
def defaults() -> Defaults:
    """Saved, as they would be after the first run."""
    save_defaults(DEFAULTS)
    return DEFAULTS


@pytest.fixture
def client(app: FastAPI, supplier: Supplier, defaults: Defaults) -> Iterator[TestClient]:
    # The context manager runs the lifespan.
    with TestClient(app, base_url="http://localhost") as c:
        yield c
