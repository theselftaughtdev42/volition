from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The database in a throwaway DATA_DIR."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    return tmp_path
