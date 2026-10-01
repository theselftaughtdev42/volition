"""The SQLite database in DATA_DIR: connections and the per-module schema migration runner."""

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from volition.core.config import data_dir
from volition.core.modules import Module


def db_path() -> Path:
    return data_dir() / "volition.db"


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """A fresh connection holding a write transaction, committed on success and rolled back on error.

    Connections are cheap and short-lived, so each call reads DATA_DIR afresh (as tests rely on).
    """
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit at the driver level so the PRAGMA below takes effect (it is a no-op inside a
    # transaction) and so the transaction boundaries are exactly the BEGIN/COMMIT here.
    conn = sqlite3.connect(path, autocommit=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


#: Core's own schema, versioned as the "core" module. Append new steps, never edit applied ones.
CORE_MIGRATIONS = (
    """
    CREATE TABLE schema_versions (
        module TEXT PRIMARY KEY,
        -- How many of the module's migrations have been applied.
        version INTEGER NOT NULL CHECK (version >= 0)
    ) STRICT;

    -- The Business model as JSON, in its single row (id is always 1) once the first run saves it.
    CREATE TABLE business (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        data TEXT NOT NULL
    ) STRICT;
    """,
)


@dataclass(frozen=True)
class Bootstrap:
    """Upgrades a database from before modules: `PRAGMA user_version` 1 and no `schema_versions`.

    Back then one user_version-numbered list held every table. The upgrade first applies each module's
    migrations up to `versions` (core's always included), creating the new tables alongside the old,
    then runs `script`, which moves the old tables' data into them and drops the old tables.
    """

    #: Module slug → how many of its migrations `script` expects to have been applied.
    versions: Mapping[str, int]
    script: str


def migrate(modules: Sequence[Module], bootstrap: Bootstrap | None = None) -> None:
    """Applies core's new migrations, then each module's in order, all in one transaction.

    `schema_versions` records how many of each module's migrations have been applied, so each list is
    append-only. On any error the database is left exactly as it was.
    """
    schemas = [("core", CORE_MIGRATIONS), *((m.slug, m.migrations) for m in modules)]
    with transaction() as conn:
        if conn.execute("PRAGMA user_version").fetchone()[0] == 1 and not _has_schema_versions(conn):
            if bootstrap is None:
                raise RuntimeError("The database predates modules and there is no upgrade for it")
            _apply(conn, [(slug, scripts[: bootstrap.versions.get(slug, 0)]) for slug, scripts in schemas])
            conn.executescript(bootstrap.script)
            # schema_versions now does the versioning; a fresh database's user_version is 0 too.
            conn.execute("PRAGMA user_version = 0")
        _apply(conn, schemas)


def _has_schema_versions(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'schema_versions'").fetchone()
        is not None
    )


def _apply(conn: sqlite3.Connection, schemas: Sequence[tuple[str, Sequence[str]]]) -> None:
    for slug, scripts in schemas:
        # Before core's first migration there is no schema_versions, so nothing has been applied.
        row = None
        if _has_schema_versions(conn):
            row = conn.execute("SELECT version FROM schema_versions WHERE module = ?", (slug,)).fetchone()
        applied = 0 if row is None else row["version"]
        if applied > len(scripts):
            raise RuntimeError(f"The database has {applied} {slug} migrations applied but only {len(scripts)} exist")
        for version, script in enumerate(scripts[applied:], start=applied + 1):
            # With autocommit=True, executescript runs inside the open transaction rather than committing it.
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_versions (module, version) VALUES (?, ?)"
                " ON CONFLICT (module) DO UPDATE SET version = excluded.version",
                (slug, version),
            )
