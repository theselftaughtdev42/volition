"""Invoice defaults: entered on the Defaults page (first on the first run) and stored in the database."""

from typing import Annotated

from pydantic import Field

from volition.clients import ClientLineItem
from volition.db import transaction
from volition.invoice import Model, Unit


class Defaults(Model):
    """Pre-filled values for the invoice form, used where the chosen client sets none.

    Everything can be overridden per invoice.
    """

    #: Number used when no invoice has been generated yet (1 → MS-0001).
    invoice_number_start: Annotated[int, Field(ge=1)]
    #: Whether the VAT box starts ticked.
    vat: bool
    unit: Unit
    line_items: list[ClientLineItem] = []
    notes: str | None = None


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
