"""The SQLite database in DATA_DIR: connections and schema migrations."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from volition.config import data_dir

#: One entry per schema version; `PRAGMA user_version` records how many have been applied.
#: Append new steps, never edit applied ones.
MIGRATIONS = [
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value ANY NOT NULL
    ) STRICT;

    CREATE TABLE clients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        contact TEXT,
        email TEXT,
        -- One line per row, newline-joined.
        address TEXT NOT NULL,
        vat INTEGER CHECK (vat IN (0, 1)),
        unit TEXT CHECK (unit IN ('days', 'hours', 'items')),
        notes TEXT
    ) STRICT;

    CREATE TABLE client_line_items (
        id INTEGER PRIMARY KEY,
        client_id TEXT NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        description TEXT NOT NULL,
        detail TEXT,
        rate INTEGER CHECK (rate >= 0),
        UNIQUE (client_id, position)
    ) STRICT;
    """,
]


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
            _migrate(conn)
            yield conn
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
        # With autocommit=True, executescript runs inside the open transaction rather than committing it.
        conn.executescript(script)
        conn.execute(f"PRAGMA user_version = {i}")


def migrate() -> None:
    """Brings the schema up to date. Every transaction does this too; calling it at startup fails fast."""
    with transaction():
        pass
