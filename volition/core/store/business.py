"""The business: entered on the Business page (first on the first run) and stored in the database."""

from volition.core.models import Business
from volition.core.store.db import transaction


def load_business() -> Business | None:
    """None until it has been saved: the app's first run."""
    with transaction() as conn:
        row = conn.execute("SELECT data FROM business").fetchone()
    return None if row is None else Business.model_validate_json(row["data"])


def save_business(business: Business) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO business (id, data) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (business.model_dump_json(by_alias=True),),
        )
