from pathlib import Path

import pytest

from volition.core.models import Business

#: A business, as the first run would save it.
BUSINESS = Business.model_validate_json((Path(__file__).resolve().parent / "fixtures" / "business.json").read_text())


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The database in a throwaway DATA_DIR."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    return tmp_path
