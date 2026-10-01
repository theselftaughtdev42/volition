"""The invoice counter: the highest invoice number generated so far."""

import sqlite3

from volition.store.db import transaction


def _last_invoice_number(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'lastInvoiceNumber'").fetchone()
    return None if row is None else row["value"]


def next_invoice_number(start: int) -> int:
    """`start` (the defaults' invoiceNumberStart) for the first invoice, then the highest issued + 1."""
    with transaction() as conn:
        last = _last_invoice_number(conn)
    return start if last is None else max(last + 1, start)


def record_invoice_number(n: int) -> None:
    """Remembers the highest number issued; regenerating an older invoice never winds it back."""
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO meta (key, value) VALUES ('lastInvoiceNumber', ?)
            ON CONFLICT (key) DO UPDATE SET value = max(value, excluded.value)
            """,
            (n,),
        )
