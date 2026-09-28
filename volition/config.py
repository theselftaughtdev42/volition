"""Loads and validates the gitignored config file (supplier.json), and where the data lives."""

import json
import os
from pathlib import Path

import pydantic

from volition.invoice import Invoice, Model, Supplier

ROOT = Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    """Read at call time so tests (and deploys) can point it elsewhere."""
    return Path(os.environ.get("CONFIG_DIR") or ROOT / "config")


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or ROOT / "data")


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
