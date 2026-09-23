"""The invoice form: default values for rendering it, and parsing a submission."""

import json
import math
import re
from datetime import date, datetime
from typing import Any, Protocol

from volition.config import Defaults, ValidationError, validate_invoice
from volition.invoice import (
    VAT_PERCENT,
    Invoice,
    Supplier,
    format_invoice_number,
    local_iso_date,
    month_period,
)
from volition.render import templates


def render_form(defaults: Defaults, supplier: Supplier, next_number: int, now: datetime | None = None) -> str:
    now = now or datetime.now()
    today = local_iso_date(now)
    period = month_period(date.fromisoformat(today))
    client = defaults.client.model_dump(by_alias=True, exclude_none=True) if defaults.client else {}
    line_items = [item.model_dump(by_alias=True, exclude_none=True) for item in defaults.line_items or []]
    return templates.get_template("form.html").render(
        supplier=supplier.model_dump(by_alias=True, exclude_none=True),
        vatPercent=VAT_PERCENT,
        values={
            "number": next_number,
            "numberFormatted": format_invoice_number(next_number),
            "issueDate": today,
            "periodStart": period.start.isoformat(),
            "periodEnd": period.end.isoformat(),
            "vat": True if defaults.vat is None else defaults.vat,
            "unit": defaults.unit or "days",
            "client": {**client, "address": "\n".join(client.get("address", []))},
            "lineItems": line_items or [{}],
            "notes": defaults.notes or "",
        },
    )


class FormBody(Protocol):
    """Starlette's FormData, or anything else with a multi-value `getlist`."""

    def getlist(self, key: str) -> list[Any]: ...


def _all(body: FormBody, key: str) -> list[str]:
    # Uploaded files are not expected anywhere in the form; treat them as blank.
    return [value.strip() if isinstance(value, str) else "" for value in body.getlist(key)]


def _one(body: FormBody, key: str) -> str:
    values = _all(body, key)
    return values[0] if values else ""


# What JavaScript's Number() accepts once trimmed (browsers only ever send the decimal form).
_JS_DECIMAL = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
_JS_RADIX = re.compile(r"0(?:[xX][0-9a-fA-F]+|[oO][0-7]+|[bB][01]+)", re.ASCII)


def _whole_number(value: str, label: str, minimum: int, errors: list[str]) -> int | None:
    n: float | None = None
    if _JS_DECIMAL.fullmatch(value):
        n = float(value)
    elif _JS_RADIX.fullmatch(value):
        n = int(value, 0)
    if n is None or not math.isfinite(n) or n != int(n) or n < minimum:
        errors.append(f"{label} must be a whole number of {minimum} or more")
        return None
    return int(n)


def parse_invoice_form(body: FormBody) -> Invoice:
    """Turns a form submission into a valid Invoice, or raises ValidationError."""
    errors: list[str] = []

    invoice_number = _whole_number(_one(body, "number"), "Invoice number", 1, errors)

    descriptions = _all(body, "description")
    details = _all(body, "detail")
    quantities = _all(body, "quantity")
    rates = _all(body, "rate")

    def at(values: list[str], i: int) -> str:
        return values[i] if i < len(values) else ""

    rows = [
        {"description": d, "detail": at(details, i), "quantity": at(quantities, i), "rate": at(rates, i)}
        for i, d in enumerate(descriptions)
    ]
    line_items = []
    # New rows arrive with the rate pre-filled, so a row is blank unless something else is set.
    for i, row in enumerate(r for r in rows if r["description"] or r["detail"] or r["quantity"]):
        label = f"Line {i + 1}"
        if not row["description"]:
            errors.append(f"{label}: description is required")
        line_items.append(
            {
                "description": row["description"],
                "detail": row["detail"] or None,
                "quantity": _whole_number(row["quantity"], f"{label}: quantity", 1, errors),
                "rate": _whole_number(row["rate"], f"{label}: rate", 0, errors),
            }
        )
    if not line_items:
        errors.append("Add at least one line item")

    period_start = _one(body, "periodStart")
    period_end = _one(body, "periodEnd")
    if period_start and period_end and period_start > period_end:
        errors.append("Period start must be on or before its end")

    if not _one(body, "issueDate"):
        errors.append("Issue date is required")
    if not _one(body, "clientName"):
        errors.append("Client name is required")
    if not _one(body, "clientAddress"):
        errors.append("Client address is required")

    if errors:
        raise ValidationError("invoice", errors)
    assert invoice_number is not None

    invoice = {
        "number": format_invoice_number(invoice_number),
        "issueDate": _one(body, "issueDate"),
        "dueDate": _one(body, "dueDate") or None,
        "period": {"start": period_start, "end": period_end} if period_start or period_end else None,
        "vat": _one(body, "vat") == "on",
        "unit": _one(body, "unit"),
        "client": {
            "name": _one(body, "clientName"),
            "contact": _one(body, "clientContact") or None,
            "address": [line.strip() for line in _one(body, "clientAddress").split("\n") if line.strip()],
            "email": _one(body, "clientEmail") or None,
        },
        "lineItems": line_items,
        "notes": _one(body, "notes") or None,
    }
    # Drop absent optional keys, then validate as JSON exactly as a stored invoice would be.
    return validate_invoice(json.dumps(_drop_none(invoice)))


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value
