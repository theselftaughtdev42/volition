"""Each module's migrations, versioned independently in schema_versions and applied at startup."""

import sqlite3
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from tests.core.test_app import fake_module
from volition.core.app import create_app
from volition.core.modules import Module
from volition.core.store import db

ASSETS = ("CREATE TABLE assets_items (name TEXT NOT NULL) STRICT;",)
SAVINGS = (
    # What had been applied when savings' first migration ran.
    """
    CREATE TABLE savings_log (entry TEXT NOT NULL) STRICT;
    INSERT INTO savings_log SELECT module || '=' || version FROM schema_versions ORDER BY module;
    """,
    "INSERT INTO savings_log VALUES ('second');",
)


def start(modules: Sequence[Module], bootstrap: db.Bootstrap | None = None) -> None:
    """Runs the app's startup, as the server does."""
    with TestClient(create_app(modules, bootstrap)):
        pass


def query(sql: str) -> list[tuple]:
    conn = sqlite3.connect(db.db_path())
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def versions() -> dict[str, int]:
    return dict(query("SELECT module, version FROM schema_versions"))


def tables() -> list[str]:
    return [name for (name,) in query("SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name")]


def modules(savings: tuple[str, ...] = SAVINGS) -> list[Module]:
    return [fake_module("assets", "Assets", ASSETS), fake_module("savings", "Savings", savings)]


def test_a_fresh_database_gets_core_then_each_module_in_registration_order() -> None:
    start(modules())
    assert versions() == {"core": 1, "assets": 1, "savings": 2}
    assert tables() == ["assets_items", "savings_log", "schema_versions"]
    assert query("SELECT entry FROM savings_log") == [("assets=1",), ("core=1",), ("second",)]


def test_migrations_apply_once() -> None:
    start(modules())
    start(modules())
    assert versions() == {"core": 1, "assets": 1, "savings": 2}
    assert len(query("SELECT entry FROM savings_log")) == 3


def test_appended_migrations_are_applied_on_the_next_startup() -> None:
    start(modules(SAVINGS[:1]))
    assert versions()["savings"] == 1
    start(modules())
    assert versions()["savings"] == 2
    assert query("SELECT entry FROM savings_log") == [("assets=1",), ("core=1",), ("second",)]


def test_a_module_added_later_gets_its_migrations() -> None:
    start([fake_module("assets", "Assets", ASSETS)])
    start(modules())
    assert versions() == {"core": 1, "assets": 1, "savings": 2}


def test_a_failing_migration_rolls_everything_back_and_fails_startup() -> None:
    start(modules(SAVINGS[:1]))
    with pytest.raises(sqlite3.OperationalError):
        start(modules((*SAVINGS, "INSERT INTO nowhere VALUES (1);")))
    assert versions() == {"core": 1, "assets": 1, "savings": 1}
    assert query("SELECT entry FROM savings_log") == [("assets=1",), ("core=1",)]


def test_a_database_newer_than_the_code_fails_startup() -> None:
    start(modules())
    with pytest.raises(RuntimeError, match="2 savings migrations applied but only 1 exist"):
        start(modules(SAVINGS[:1]))


# --- Databases from before modules ---


def seed_pre_module_database() -> None:
    """One user_version-numbered list held every table."""
    conn = sqlite3.connect(db.db_path())
    conn.executescript("CREATE TABLE things (name TEXT); INSERT INTO things VALUES ('old'); PRAGMA user_version = 1;")
    conn.close()


BOOTSTRAP = db.Bootstrap(
    versions={"core": 1, "savings": 1},
    script="INSERT INTO savings_log SELECT 'moved ' || name FROM things; DROP TABLE things;",
)


def test_a_pre_module_database_is_bootstrapped_then_migrated_as_usual() -> None:
    db.db_path().parent.mkdir(parents=True)
    seed_pre_module_database()
    start(modules(), BOOTSTRAP)
    assert versions() == {"core": 1, "assets": 1, "savings": 2}
    # Assets wasn't in the bootstrap's versions, so got its migration after savings' first.
    assert query("SELECT entry FROM savings_log") == [("core=1",), ("moved old",), ("second",)]
    assert tables() == ["assets_items", "savings_log", "schema_versions"]
    assert query("PRAGMA user_version") == [(0,)]


def test_a_pre_module_database_without_a_bootstrap_fails_startup_untouched() -> None:
    db.db_path().parent.mkdir(parents=True)
    seed_pre_module_database()
    with pytest.raises(RuntimeError, match="predates modules"):
        start(modules())
    assert tables() == ["things"]
