"""The invoicing settings: entered on the Settings page (first on invoicing's first run) and stored in the database."""

from volition.core.store.db import transaction
from volition.invoicing.models import InvoicingSettings


def load_settings() -> InvoicingSettings | None:
    """None until they have been saved: invoicing's first run."""
    with transaction() as conn:
        row = conn.execute("SELECT data FROM invoicing_settings").fetchone()
    return None if row is None else InvoicingSettings.model_validate_json(row["data"])


def save_settings(settings: InvoicingSettings) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO invoicing_settings (id, data) VALUES (1, ?)"
            " ON CONFLICT (id) DO UPDATE SET data = excluded.data",
            (settings.model_dump_json(by_alias=True),),
        )
