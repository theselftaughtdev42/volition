import shutil
from pathlib import Path

import pytest

from volition.invoice import Invoice, Supplier

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Counter in a throwaway DATA_DIR; CONFIG_DIR holds copies of the example configs."""
    config = tmp_path / "config"
    config.mkdir()
    shutil.copy(ROOT / "config/supplier.example.json", config / "supplier.json")
    shutil.copy(ROOT / "config/defaults.example.json", config / "defaults.json")
    monkeypatch.setenv("CONFIG_DIR", str(config))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def invoice() -> Invoice:
    return Invoice.model_validate_json((FIXTURES / "invoice.json").read_text())


@pytest.fixture
def supplier() -> Supplier:
    return Supplier.model_validate_json((ROOT / "config/supplier.example.json").read_text())
