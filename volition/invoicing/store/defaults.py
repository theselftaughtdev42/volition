"""Invoice defaults: entered on the Defaults page (first on the first run) and stored in the database."""

from volition.core.store.db import transaction
from volition.invoicing.models import Defaults


def load_defaults() -> Defaults | None:
    """None until they have been saved: the app's first run."""
    with transaction() as conn:
        row = conn.execute("SELECT data FROM invoicing_defaults").fetchone()
    return None if row is None else Defaults.model_validate_json(row["data"])


def save_defaults(defaults: Defaults) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO invoicing_defaults (id, data) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (defaults.model_dump_json(by_alias=True),),
        )
