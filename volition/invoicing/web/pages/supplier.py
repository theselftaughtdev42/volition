"""The supplier form (/supplier): who invoices are from, first on the first run."""

import re
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from volition.core.errors import ValidationError
from volition.core.web.deps import FormDep
from volition.core.web.forms import FormBody, field, lines, validate_form, whole_number
from volition.invoicing.models import Supplier
from volition.invoicing.store.supplier import load_supplier, save_supplier
from volition.invoicing.web.pages import render_page

router = APIRouter()


@router.get("/supplier", response_class=HTMLResponse)
def supplier_form() -> HTMLResponse:
    supplier = load_supplier()
    return HTMLResponse(render_supplier_form(supplier, supplier_form_values(supplier), first_run=supplier is None))


@router.post("/supplier", response_model=None)
def set_supplier(form: FormDep) -> Response:
    try:
        save_supplier(parse_supplier_form(form))
    except ValidationError as e:
        supplier = load_supplier()
        html = render_supplier_form(supplier, submitted_supplier_values(form), supplier is None, e.errors)
        return HTMLResponse(html, status_code=422)
    # On the first run, / then redirects on to the defaults.
    return RedirectResponse("/", status_code=303)


def render_supplier_form(
    supplier: Supplier | None, values: dict[str, Any], first_run: bool, errors: list[str] | None = None
) -> str:
    """`supplier` is the stored one (None on the first run), for the header; `values` are what the form shows."""
    return render_page(
        "supplier.html",
        "/supplier",
        supplier,
        values=values,
        first_run=first_run,
        errors=errors or [],
    )


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
    "bankName",
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
    return {key: field(body, key) for key in _SUPPLIER_FIELDS}


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
        "bankName": "Bank",
        "accountName": "Account name",
    }
    for key, label in required.items():
        if not field(body, key):
            errors.append(f"{label} is required")
    if not lines(field(body, "address")):
        errors.append("Address is required")
    terms = whole_number(field(body, "paymentTermsDays"), "Payment terms", 0, errors)
    sort_code = _digits(field(body, "sortCode"))
    if not re.fullmatch(r"[0-9]{6}", sort_code):
        errors.append("Sort code must be 6 digits")
    account_number = _digits(field(body, "accountNumber"))
    if not re.fullmatch(r"[0-9]{8}", account_number):
        errors.append("Account number must be 8 digits")
    if errors:
        raise ValidationError("supplier", errors)

    supplier = {
        "name": field(body, "name"),
        "legalName": field(body, "legalName"),
        "address": lines(field(body, "address")),
        "website": field(body, "website") or None,
        "email": field(body, "email"),
        "companyNumber": field(body, "companyNumber"),
        "registeredIn": field(body, "registeredIn"),
        "vatNumber": field(body, "vatNumber") or None,
        "paymentTermsDays": terms,
        "bank": {
            "bankName": field(body, "bankName"),
            "accountName": field(body, "accountName"),
            "sortCode": "-".join(sort_code[i : i + 2] for i in range(0, 6, 2)),
            "accountNumber": account_number,
        },
    }
    return validate_form(Supplier, supplier, "supplier")
