"""The supplier (who invoices are from): entered on the Supplier page (first on the first run) and stored in the database."""

from volition.db import transaction
from volition.invoice import Supplier


def load_supplier() -> Supplier | None:
    """None until it has been saved: the app's first run."""
    with transaction() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'supplier'").fetchone()
    return None if row is None else Supplier.model_validate_json(row["value"])


def save_supplier(supplier: Supplier) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('supplier', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (supplier.model_dump_json(by_alias=True),),
        )
