"""The invoicing settings form (/invoicing/settings): invoice defaults, payment terms and bank details, first on
invoicing's first run."""

import re
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from volition.core.errors import ValidationError
from volition.core.web.deps import FormDep
from volition.core.web.forms import FormBody, field, validate_form, whole_number
from volition.core.web.shell import Shell, ShellDep
from volition.invoicing.invoices import VAT_PERCENT
from volition.invoicing.models import InvoicingSettings
from volition.invoicing.store.settings import load_settings, save_settings
from volition.invoicing.web.forms import parse_preset_lines, submitted_preset_lines
from volition.invoicing.web.pages import PREFIX, render_page

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_form(shell: ShellDep) -> HTMLResponse:
    settings = load_settings()
    values = settings_form_values(settings)
    return HTMLResponse(render_settings_form(shell, values, first_run=settings is None))


@router.post("/settings", response_model=None)
def set_settings(form: FormDep, shell: ShellDep) -> Response:
    try:
        save_settings(parse_settings_form(form))
    except ValidationError as e:
        first_run = load_settings() is None
        html = render_settings_form(shell, submitted_settings_values(form), first_run, e.errors)
        return HTMLResponse(html, status_code=422)
    return RedirectResponse(f"{PREFIX}/", status_code=303)


def render_settings_form(shell: Shell, values: dict[str, Any], first_run: bool, errors: list[str] | None = None) -> str:
    return render_page(
        "settings.html",
        shell,
        vatPercent=VAT_PERCENT,
        values=values,
        first_run=first_run,
        errors=errors or [],
    )


def settings_form_values(settings: InvoicingSettings | None = None) -> dict[str, Any]:
    """Values for the settings form: the stored settings, or starting suggestions on the first run.

    The bank details are flattened into the form alongside everything else.
    """
    if settings is None:
        return {
            "invoiceNumberStart": 1,
            "vat": True,
            "unit": "days",
            "lineItems": [{}],
            "notes": "",
            "paymentTermsDays": 30,
        }
    data = settings.model_dump(by_alias=True, exclude_none=True)
    return {**data, **data.pop("bank"), "lineItems": data["lineItems"] or [{}], "notes": settings.notes or ""}


_TEXT_FIELDS = [
    "invoiceNumberStart",
    "unit",
    "notes",
    "paymentTermsDays",
    "bankName",
    "accountName",
    "sortCode",
    "accountNumber",
]


def submitted_settings_values(body: FormBody) -> dict[str, Any]:
    """A settings form submission as values for re-rendering it alongside its errors."""
    return {
        **{key: field(body, key) for key in _TEXT_FIELDS},
        "vat": field(body, "vat") == "on",
        "lineItems": submitted_preset_lines(body),
    }


def _digits(value: str) -> str:
    """Bank numbers as people type them, e.g. "12-34-56" or "1234 5678", without the separators."""
    return re.sub(r"[\s-]", "", value)


def parse_settings_form(body: FormBody) -> InvoicingSettings:
    """Turns a settings form submission into valid InvoicingSettings, or raises ValidationError."""
    errors: list[str] = []
    start = whole_number(field(body, "invoiceNumberStart"), "First invoice number", 1, errors)
    line_items = parse_preset_lines(body, errors)
    terms = whole_number(field(body, "paymentTermsDays"), "Payment terms", 0, errors)
    for key, label in {"bankName": "Bank", "accountName": "Account name"}.items():
        if not field(body, key):
            errors.append(f"{label} is required")
    sort_code = _digits(field(body, "sortCode"))
    if not re.fullmatch(r"[0-9]{6}", sort_code):
        errors.append("Sort code must be 6 digits")
    account_number = _digits(field(body, "accountNumber"))
    if not re.fullmatch(r"[0-9]{8}", account_number):
        errors.append("Account number must be 8 digits")
    if errors:
        raise ValidationError("settings", errors)

    settings = {
        "invoiceNumberStart": start,
        # An unticked checkbox is absent from the submission.
        "vat": field(body, "vat") == "on",
        "unit": field(body, "unit"),
        "lineItems": line_items,
        "notes": field(body, "notes") or None,
        "paymentTermsDays": terms,
        "bank": {
            "bankName": field(body, "bankName"),
            "accountName": field(body, "accountName"),
            "sortCode": "-".join(sort_code[i : i + 2] for i in range(0, 6, 2)),
            "accountNumber": account_number,
        },
    }
    return validate_form(InvoicingSettings, settings, "settings")
