"""Where the data lives, and validation errors in a form the pages and API can report."""

import os
from pathlib import Path

import pydantic

from volition.invoice import Invoice, Model

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Read at call time so tests (and deploys) can point it elsewhere."""
    return Path(os.environ.get("DATA_DIR") or ROOT / "data")


def allowed_hosts() -> list[str]:
    """Host headers the app answers to, from comma-separated ALLOWED_HOSTS ("*" allows any).

    Guards against DNS rebinding, where another site's domain is pointed at this machine.
    """
    hosts = os.environ.get("ALLOWED_HOSTS") or "127.0.0.1,localhost,[::1]"
    return [host.strip().lower() for host in hosts.split(",") if host.strip()]


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
