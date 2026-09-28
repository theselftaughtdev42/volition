import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from volition.clients import ClientLineItem
from volition.defaults import Defaults, save_defaults
from volition.invoice import Invoice, Supplier
from volition.main import app

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The database in a throwaway DATA_DIR; CONFIG_DIR holds a copy of the example supplier config."""
    config = tmp_path / "config"
    config.mkdir()
    shutil.copy(ROOT / "config/supplier.example.json", config / "supplier.json")
    monkeypatch.setenv("CONFIG_DIR", str(config))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def invoice() -> Invoice:
    return Invoice.model_validate_json((FIXTURES / "invoice.json").read_text())


@pytest.fixture
def supplier() -> Supplier:
    return Supplier.model_validate_json((ROOT / "config/supplier.example.json").read_text())


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
def client(defaults: Defaults) -> Iterator[TestClient]:
    # The context manager runs the lifespan.
    with TestClient(app) as c:
        yield c
