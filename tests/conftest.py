from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from volition.clients import ClientLineItem
from volition.defaults import Defaults, save_defaults
from volition.invoice import Invoice, Supplier
from volition.main import app
from volition.supplier import save_supplier

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The database in a throwaway DATA_DIR."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    return tmp_path


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
    line_items=[ClientLineItem(description="IT & Software Consultancy Services", rate=650)],
)


@pytest.fixture
def defaults() -> Defaults:
    """Saved, as they would be after the first run."""
    save_defaults(DEFAULTS)
    return DEFAULTS


@pytest.fixture
def client(supplier: Supplier, defaults: Defaults) -> Iterator[TestClient]:
    # The context manager runs the lifespan.
    with TestClient(app, base_url="http://localhost") as c:
        yield c
