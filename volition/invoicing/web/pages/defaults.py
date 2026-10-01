"""The invoice defaults form (/invoicing/defaults), second on the first run."""

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from volition.core.errors import ValidationError
from volition.core.web.deps import FormDep
from volition.core.web.forms import FormBody, field, validate_form, whole_number
from volition.core.web.shell import Shell, ShellDep
from volition.invoicing.invoices import VAT_PERCENT
from volition.invoicing.models import Defaults, Supplier
from volition.invoicing.store.defaults import load_defaults, save_defaults
from volition.invoicing.web.deps import SupplierDep
from volition.invoicing.web.forms import parse_preset_lines, submitted_preset_lines
from volition.invoicing.web.pages import PREFIX, render_page

router = APIRouter()


@router.get("/defaults", response_class=HTMLResponse)
def defaults_form(shell: ShellDep, supplier: SupplierDep) -> HTMLResponse:
    defaults = load_defaults()
    values = defaults_form_values(defaults)
    return HTMLResponse(render_defaults_form(shell, supplier, values, first_run=defaults is None))


@router.post("/defaults", response_model=None)
def set_defaults(form: FormDep, shell: ShellDep, supplier: SupplierDep) -> Response:
    try:
        save_defaults(parse_defaults_form(form))
    except ValidationError as e:
        first_run = load_defaults() is None
        html = render_defaults_form(shell, supplier, submitted_defaults_values(form), first_run, e.errors)
        return HTMLResponse(html, status_code=422)
    return RedirectResponse(f"{PREFIX}/", status_code=303)


def render_defaults_form(
    shell: Shell, supplier: Supplier, values: dict[str, Any], first_run: bool, errors: list[str] | None = None
) -> str:
    return render_page(
        "defaults.html",
        shell,
        supplier,
        vatPercent=VAT_PERCENT,
        values=values,
        first_run=first_run,
        errors=errors or [],
    )


def defaults_form_values(defaults: Defaults | None = None) -> dict[str, Any]:
    """Values for the defaults form: the stored defaults, or starting suggestions on the first run."""
    if defaults is None:
        return {"invoiceNumberStart": 1, "vat": True, "unit": "days", "lineItems": [{}], "notes": ""}
    data = defaults.model_dump(by_alias=True, exclude_none=True)
    return {**data, "lineItems": data["lineItems"] or [{}], "notes": defaults.notes or ""}


def submitted_defaults_values(body: FormBody) -> dict[str, Any]:
    """A defaults form submission as values for re-rendering it alongside its errors."""
    return {
        "invoiceNumberStart": field(body, "invoiceNumberStart"),
        "vat": field(body, "vat") == "on",
        "unit": field(body, "unit"),
        "lineItems": submitted_preset_lines(body),
        "notes": field(body, "notes"),
    }


def parse_defaults_form(body: FormBody) -> Defaults:
    """Turns a defaults form submission into valid Defaults, or raises ValidationError."""
    errors: list[str] = []
    start = whole_number(field(body, "invoiceNumberStart"), "First invoice number", 1, errors)
    line_items = parse_preset_lines(body, errors)
    if errors:
        raise ValidationError("defaults", errors)

    defaults = {
        "invoiceNumberStart": start,
        # An unticked checkbox is absent from the submission.
        "vat": field(body, "vat") == "on",
        "unit": field(body, "unit"),
        "lineItems": line_items,
        "notes": field(body, "notes") or None,
    }
    return validate_form(Defaults, defaults, "defaults")
