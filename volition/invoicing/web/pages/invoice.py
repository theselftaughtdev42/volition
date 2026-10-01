"""The invoice form (GET /) and the PDF it generates (POST /invoice)."""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

from volition.core.errors import ValidationError
from volition.core.web.deps import FormDep
from volition.core.web.forms import FormBody, field, field_values, validate_form, whole_number
from volition.invoicing.invoices import (
    VAT_PERCENT,
    format_invoice_number,
    local_iso_date,
    month_period,
    parse_invoice_number,
)
from volition.invoicing.models import ClientRecord, Defaults, Invoice, Supplier
from volition.invoicing.pdf import render_pdf
from volition.invoicing.store.clients import get_client, list_clients
from volition.invoicing.store.invoice_numbers import next_invoice_number, record_invoice_number
from volition.invoicing.web.deps import DefaultsDep, SupplierDep
from volition.invoicing.web.pages import render_page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def invoice_form(defaults: DefaultsDep, supplier: SupplierDep) -> HTMLResponse:
    next_number = next_invoice_number(defaults.invoice_number_start)
    return HTMLResponse(render_form(defaults, supplier, next_number, list_clients()))


# A plain `def`, so FastAPI runs it on a worker thread: rendering and file I/O block.
@router.post("/invoice")
def create_invoice(form: FormDep, supplier: SupplierDep) -> Response:
    invoice = parse_invoice_form(form, get_client)
    pdf = render_pdf(invoice, supplier)
    # Only count the number once the PDF actually exists.
    record_invoice_number(parse_invoice_number(invoice.number))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'},
    )


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
    return render_page(
        "form.html",
        "/",
        supplier,
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


def parse_invoice_form(body: FormBody, find_client: Callable[[str], ClientRecord | None]) -> Invoice:
    """Turns a form submission into a valid Invoice, or raises ValidationError.

    The client is billed as stored, looked up by the submitted clientId.
    """
    errors: list[str] = []

    invoice_number = whole_number(field(body, "number"), "Invoice number", 1, errors)

    descriptions = field_values(body, "description")
    details = field_values(body, "detail")
    quantities = field_values(body, "quantity")
    rates = field_values(body, "rate")

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
                "quantity": whole_number(row["quantity"], f"{label}: quantity", 1, errors),
                "rate": whole_number(row["rate"], f"{label}: rate", 0, errors),
            }
        )
    if not line_items:
        errors.append("Add at least one line item")

    period_start = field(body, "periodStart")
    period_end = field(body, "periodEnd")
    if period_start and period_end and period_start > period_end:
        errors.append("Period start must be on or before its end")

    if not field(body, "issueDate"):
        errors.append("Issue date is required")
    client_id = field(body, "clientId")
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
        "issueDate": field(body, "issueDate"),
        "dueDate": field(body, "dueDate") or None,
        "period": {"start": period_start, "end": period_end} if period_start or period_end else None,
        "vat": field(body, "vat") == "on",
        "unit": field(body, "unit"),
        "client": client.bill_to().model_dump(mode="json", by_alias=True),
        "lineItems": line_items,
        "notes": field(body, "notes") or None,
    }
    return validate_form(Invoice, invoice, "invoice")
