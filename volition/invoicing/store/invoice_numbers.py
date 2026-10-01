"""The invoice counter: the highest invoice number generated so far."""

import sqlite3

from volition.core.store.db import transaction


def _last_invoice_number(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT last_invoice_number FROM invoicing_counter").fetchone()
    return None if row is None else row["last_invoice_number"]


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
            INSERT INTO invoicing_counter (id, last_invoice_number) VALUES (1, ?)
            ON CONFLICT (id) DO UPDATE SET last_invoice_number = max(last_invoice_number, excluded.last_invoice_number)
            """,
            (n,),
        )
