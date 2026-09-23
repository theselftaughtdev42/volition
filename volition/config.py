"""Loads and validates the gitignored config files, and persists the invoice counter."""

import json
import os
from pathlib import Path
from typing import Annotated

import pydantic
from pydantic import EmailStr, Field

from volition.invoice import Invoice, Model, Supplier, Unit

ROOT = Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    """Read at call time so tests (and deploys) can point it elsewhere."""
    return Path(os.environ.get("CONFIG_DIR") or ROOT / "config")


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or ROOT / "data")


class DefaultsClient(Model):
    name: str | None = None
    contact: str | None = None
    address: list[str] | None = None
    email: EmailStr | None = None


class DefaultsLineItem(Model):
    description: str | None = None
    detail: str | None = None
    quantity: Annotated[int, Field(ge=1)] | None = None
    rate: Annotated[int, Field(ge=0)] | None = None


class Defaults(Model):
    """Pre-filled values for the invoice form. Everything can be overridden per invoice."""

    #: Number used when no invoice has been generated yet (1 → MS-0001).
    invoice_number_start: Annotated[int, Field(ge=1)]
    #: Whether the VAT box starts ticked.
    vat: bool | None = None
    unit: Unit | None = None
    client: DefaultsClient | None = None
    line_items: list[DefaultsLineItem] | None = None
    notes: str | None = None


class ValidationError(Exception):
    def __init__(self, what: str, errors: list[str]) -> None:
        super().__init__(f"Invalid {what}:\n  " + "\n  ".join(errors))
        self.errors = errors


def describe(err: pydantic.ValidationError) -> list[str]:
    """Pydantic errors as "<json pointer> <message>", e.g. "/lineItems/0/rate Input should be ..."."""
    messages = []
    for e in err.errors(include_url=False):
        loc = "".join(f"/{part}" for part in e["loc"]) or "(root)"
        messages.append(f"{loc} {e['msg']}")
    return messages


def _validate[M: Model](model: type[M], json_text: str | bytes, what: str) -> M:
    try:
        return model.model_validate_json(json_text)
    except pydantic.ValidationError as e:
        raise ValidationError(what, describe(e)) from None


def validate_invoice(json_text: str | bytes) -> Invoice:
    return _validate(Invoice, json_text, "invoice")


def _load_config[M: Model](model: type[M], file: str) -> M:
    path = config_dir() / file
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Copy {file.replace('.json', '.example.json')} and fill it in.")
    text = path.read_text(encoding="utf-8")
    json.loads(text)  # Surface malformed JSON as a JSON error rather than a validation error.
    return _validate(model, text, str(path))


def load_supplier() -> Supplier:
    """Read on every request so edits to the config files apply without a restart."""
    return _load_config(Supplier, "supplier.json")


def load_defaults() -> Defaults:
    return _load_config(Defaults, "defaults.json")


def _state_file() -> Path:
    return data_dir() / "state.json"


def _last_invoice_number() -> int | None:
    path = _state_file()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("lastInvoiceNumber")


def next_invoice_number(defaults: Defaults) -> int:
    last = _last_invoice_number()
    return defaults.invoice_number_start if last is None else max(last + 1, defaults.invoice_number_start)


def record_invoice_number(n: int) -> None:
    """Remembers the highest number issued; regenerating an older invoice never winds it back."""
    last = _last_invoice_number() or 0
    if n <= last:
        return
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps({"lastInvoiceNumber": n}, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
