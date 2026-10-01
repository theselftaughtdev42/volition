"""The SQLite database in DATA_DIR: connections and the schema migration runner."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from volition.core.config import data_dir


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


def migrate(migrations: Sequence[str]) -> None:
    """Applies the scripts `PRAGMA user_version` says are new, in one transaction.

    `user_version` counts the scripts applied so far, so `migrations` is append-only.
    """
    with transaction() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(migrations[version:], start=version + 1):
            # With autocommit=True, executescript runs inside the open transaction rather than committing it.
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {i}")
