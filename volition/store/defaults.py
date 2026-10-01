"""Invoice defaults: entered on the Defaults page (first on the first run) and stored in the database."""

from volition.models import Defaults
from volition.store.db import transaction


def load_defaults() -> Defaults | None:
    """None until they have been saved: the app's first run."""
    with transaction() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'defaults'").fetchone()
    return None if row is None else Defaults.model_validate_json(row["value"])


def save_defaults(defaults: Defaults) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('defaults', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (defaults.model_dump_json(by_alias=True),),
        )
