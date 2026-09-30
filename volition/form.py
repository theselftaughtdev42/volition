"""The invoice, client, defaults and supplier forms: values for rendering them, and parsing submissions."""

import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Protocol

import pydantic

from volition.clients import ClientDetails, ClientRecord
from volition.config import ValidationError, describe, validate_invoice
from volition.defaults import Defaults
from volition.invoice import (
    VAT_PERCENT,
    Invoice,
    Supplier,
    format_invoice_number,
    local_iso_date,
    month_period,
)
from volition.render import templates


def _invoice_presets(defaults: Defaults, client: ClientRecord | None = None) -> dict[str, Any]:
    """The fields choosing a client fills: the client's own defaults, else the global ones."""
    line_items = (client.line_items if client else None) or defaults.line_items
    notes = client.notes if client and client.notes is not None else defaults.notes
    return {
        "vat": client.vat if client and client.vat is not None else defaults.vat,
        "unit": (client.unit if client else None) or defaults.unit,
        "lineItems": [item.model_dump(by_alias=True, exclude_none=True) for item in line_items] or [{}],
        "notes": notes or "",
    }


def _client_option(client: ClientRecord, defaults: Defaults) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        # What the Bill-to summary shows, one line each.
        "billTo": [line for line in [client.contact, *client.address, client.email] if line],
        **_invoice_presets(defaults, client),
    }


def render_form(
    defaults: Defaults,
    supplier: Supplier,
    next_number: int,
    clients: list[ClientRecord],
    now: datetime | None = None,
) -> str:
    now = now or datetime.now()
    today = local_iso_date(now)
    period = month_period(date.fromisoformat(today))
    options = [_client_option(client, defaults) for client in clients]
    # A lone client is preselected; with several, choosing is required so no one is billed by accident.
    selected = options[0] if len(options) == 1 else None
    return templates.get_template("form.html").render(
        page="invoice",
        supplier=supplier.model_dump(by_alias=True, exclude_none=True),
        vatPercent=VAT_PERCENT,
        clients=options,
        values={
            "number": next_number,
            "numberFormatted": format_invoice_number(next_number),
            "issueDate": today,
            "periodStart": period.start.isoformat(),
            "periodEnd": period.end.isoformat(),
            "client": selected,
            **(selected or _invoice_presets(defaults)),
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


def parse_invoice_form(body: FormBody, find_client: Callable[[str], ClientRecord | None]) -> Invoice:
    """Turns a form submission into a valid Invoice, or raises ValidationError.

    The client is billed as stored, looked up by the submitted clientId.
    """
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
    client_id = _one(body, "clientId")
    client = find_client(client_id) if client_id else None
    if not client_id:
        errors.append("Choose a client")
    elif client is None:
        errors.append("That client no longer exists; reload the page")

    if errors:
        raise ValidationError("invoice", errors)
    assert invoice_number is not None and client is not None

    invoice = {
        "number": format_invoice_number(invoice_number),
        "issueDate": _one(body, "issueDate"),
        "dueDate": _one(body, "dueDate") or None,
        "period": {"start": period_start, "end": period_end} if period_start or period_end else None,
        "vat": _one(body, "vat") == "on",
        "unit": _one(body, "unit"),
        "client": client.bill_to().model_dump(mode="json", by_alias=True),
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


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def client_form_values(client: ClientRecord | None = None) -> dict[str, Any]:
    """Values for the client form: a stored client's, or blanks for a new one."""
    if client is None:
        return {"address": "", "vat": "", "unit": "", "lineItems": [{}], "notes": ""}
    data = client.model_dump(by_alias=True, exclude_none=True)
    return {
        **data,
        "address": "\n".join(client.address),
        "vat": "" if client.vat is None else "yes" if client.vat else "no",
        "unit": client.unit or "",
        "lineItems": data["lineItems"] or [{}],
    }


def _submitted_line_items(body: FormBody) -> list[dict[str, str]]:
    rows = zip(_all(body, "description"), _all(body, "detail"), _all(body, "rate"), strict=False)
    return [{"description": d, "detail": dt, "rate": r} for d, dt, r in rows] or [{}]


def _parse_line_items(body: FormBody, errors: list[str]) -> list[dict[str, Any]]:
    """Preset line items (no quantity), skipping blank rows."""
    line_items = []
    for i, row in enumerate(r for r in _submitted_line_items(body) if any(r.values())):
        label = f"Line {i + 1}"
        if not row["description"]:
            errors.append(f"{label}: description is required")
        rate = _whole_number(row["rate"], f"{label}: rate", 0, errors) if row["rate"] else None
        line_items.append({"description": row["description"], "detail": row["detail"] or None, "rate": rate})
    return line_items


def _validate_form[M: pydantic.BaseModel](model: type[M], data: dict[str, Any], what: str) -> M:
    try:
        return model.model_validate_json(json.dumps(_drop_none(data)))
    except pydantic.ValidationError as e:
        raise ValidationError(what, describe(e)) from None


def submitted_client_values(body: FormBody) -> dict[str, Any]:
    """A client form submission as values for re-rendering it, e.g. alongside its errors."""
    return {
        **{key: _one(body, key) for key in ["name", "contact", "email", "address", "vat", "unit", "notes"]},
        "lineItems": _submitted_line_items(body),
    }


def parse_client_form(body: FormBody) -> ClientDetails:
    """Turns a client form submission into valid ClientDetails, or raises ValidationError."""
    errors: list[str] = []
    if not _one(body, "name"):
        errors.append("Name is required")
    if not _lines(_one(body, "address")):
        errors.append("Address is required")
    line_items = _parse_line_items(body, errors)
    if errors:
        raise ValidationError("client", errors)

    vat = _one(body, "vat")
    client = {
        "name": _one(body, "name"),
        "contact": _one(body, "contact") or None,
        "address": _lines(_one(body, "address")),
        "email": _one(body, "email") or None,
        "vat": {"yes": True, "no": False}.get(vat, vat or None),
        "unit": _one(body, "unit") or None,
        "lineItems": line_items,
        "notes": _one(body, "notes") or None,
    }
    return _validate_form(ClientDetails, client, "client")


def defaults_form_values(defaults: Defaults | None = None) -> dict[str, Any]:
    """Values for the defaults form: the stored defaults, or starting suggestions on the first run."""
    if defaults is None:
        return {"invoiceNumberStart": 1, "vat": True, "unit": "days", "lineItems": [{}], "notes": ""}
    data = defaults.model_dump(by_alias=True, exclude_none=True)
    return {**data, "lineItems": data["lineItems"] or [{}], "notes": defaults.notes or ""}


def submitted_defaults_values(body: FormBody) -> dict[str, Any]:
    """A defaults form submission as values for re-rendering it alongside its errors."""
    return {
        "invoiceNumberStart": _one(body, "invoiceNumberStart"),
        "vat": _one(body, "vat") == "on",
        "unit": _one(body, "unit"),
        "lineItems": _submitted_line_items(body),
        "notes": _one(body, "notes"),
    }


def parse_defaults_form(body: FormBody) -> Defaults:
    """Turns a defaults form submission into valid Defaults, or raises ValidationError."""
    errors: list[str] = []
    start = _whole_number(_one(body, "invoiceNumberStart"), "First invoice number", 1, errors)
    line_items = _parse_line_items(body, errors)
    if errors:
        raise ValidationError("defaults", errors)

    defaults = {
        "invoiceNumberStart": start,
        # An unticked checkbox is absent from the submission.
        "vat": _one(body, "vat") == "on",
        "unit": _one(body, "unit"),
        "lineItems": line_items,
        "notes": _one(body, "notes") or None,
    }
    return _validate_form(Defaults, defaults, "defaults")


_SUPPLIER_FIELDS = [
    "name",
    "legalName",
    "address",
    "website",
    "email",
    "companyNumber",
    "registeredIn",
    "vatNumber",
    "paymentTermsDays",
    "accountName",
    "sortCode",
    "accountNumber",
]


def supplier_form_values(supplier: Supplier | None = None) -> dict[str, Any]:
    """Values for the supplier form: the stored supplier, or starting suggestions on the first run.

    The bank details are flattened into the form alongside everything else.
    """
    if supplier is None:
        return {"paymentTermsDays": 30}
    data = supplier.model_dump(by_alias=True, exclude_none=True)
    return {**data, **data.pop("bank"), "address": "\n".join(supplier.address)}


def submitted_supplier_values(body: FormBody) -> dict[str, Any]:
    """A supplier form submission as values for re-rendering it alongside its errors."""
    return {key: _one(body, key) for key in _SUPPLIER_FIELDS}


def _digits(value: str) -> str:
    """Bank numbers as people type them, e.g. "12-34-56" or "1234 5678", without the separators."""
    return re.sub(r"[\s-]", "", value)


def parse_supplier_form(body: FormBody) -> Supplier:
    """Turns a supplier form submission into a valid Supplier, or raises ValidationError."""
    errors: list[str] = []
    required = {
        "name": "Trading name",
        "legalName": "Legal name",
        "email": "Email",
        "companyNumber": "Company number",
        "registeredIn": "Registered in",
        "accountName": "Account name",
    }
    for key, label in required.items():
        if not _one(body, key):
            errors.append(f"{label} is required")
    if not _lines(_one(body, "address")):
        errors.append("Address is required")
    terms = _whole_number(_one(body, "paymentTermsDays"), "Payment terms", 0, errors)
    sort_code = _digits(_one(body, "sortCode"))
    if not re.fullmatch(r"[0-9]{6}", sort_code):
        errors.append("Sort code must be 6 digits")
    account_number = _digits(_one(body, "accountNumber"))
    if not re.fullmatch(r"[0-9]{8}", account_number):
        errors.append("Account number must be 8 digits")
    if errors:
        raise ValidationError("supplier", errors)

    supplier = {
        "name": _one(body, "name"),
        "legalName": _one(body, "legalName"),
        "address": _lines(_one(body, "address")),
        "website": _one(body, "website") or None,
        "email": _one(body, "email"),
        "companyNumber": _one(body, "companyNumber"),
        "registeredIn": _one(body, "registeredIn"),
        "vatNumber": _one(body, "vatNumber") or None,
        "paymentTermsDays": terms,
        "bank": {
            "accountName": _one(body, "accountName"),
            "sortCode": "-".join(sort_code[i : i + 2] for i in range(0, 6, 2)),
            "accountNumber": account_number,
        },
    }
    return _validate_form(Supplier, supplier, "supplier")


def render_clients(supplier: Supplier, clients: list[ClientRecord]) -> str:
    return templates.get_template("clients.html").render(
        page="clients",
        supplier=supplier.model_dump(by_alias=True, exclude_none=True),
        clients=[client.model_dump(by_alias=True, exclude_none=True) for client in clients],
    )


def render_client_form(
    supplier: Supplier, values: dict[str, Any], client_id: str | None = None, errors: list[str] | None = None
) -> str:
    return templates.get_template("client.html").render(
        page="clients",
        supplier=supplier.model_dump(by_alias=True, exclude_none=True),
        vatPercent=VAT_PERCENT,
        values=values,
        client_id=client_id,
        errors=errors or [],
    )


def render_defaults_form(
    supplier: Supplier, values: dict[str, Any], first_run: bool, errors: list[str] | None = None
) -> str:
    return templates.get_template("defaults.html").render(
        page="defaults",
        supplier=supplier.model_dump(by_alias=True, exclude_none=True),
        vatPercent=VAT_PERCENT,
        values=values,
        first_run=first_run,
        errors=errors or [],
    )


def render_supplier_form(
    supplier: Supplier | None, values: dict[str, Any], first_run: bool, errors: list[str] | None = None
) -> str:
    """`supplier` is the stored one (None on the first run), for the header; `values` are what the form shows."""
    return templates.get_template("supplier.html").render(
        page="supplier",
        supplier=supplier and supplier.model_dump(by_alias=True, exclude_none=True),
        values=values,
        first_run=first_run,
        errors=errors or [],
    )
