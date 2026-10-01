"""The supplier (who invoices are from): entered on the Supplier page (first on the first run) and stored in the database."""

from volition.core.store.db import transaction
from volition.invoicing.models import Supplier


def load_supplier() -> Supplier | None:
    """None until it has been saved: the app's first run."""
    with transaction() as conn:
        row = conn.execute("SELECT data FROM invoicing_supplier").fetchone()
    return None if row is None else Supplier.model_validate_json(row["data"])


def save_supplier(supplier: Supplier) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO invoicing_supplier (id, data) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (supplier.model_dump_json(by_alias=True),),
        )
