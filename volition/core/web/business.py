"""The Business page (/business): the business's identity, first on the first run."""

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from volition.core.errors import ValidationError
from volition.core.models import Business
from volition.core.store.business import load_business, save_business
from volition.core.templates import templates
from volition.core.web.deps import BUSINESS_PATH, FormDep
from volition.core.web.forms import FormBody, field, lines, validate_form
from volition.core.web.shell import Shell, ShellDep

router = APIRouter()


@router.get(BUSINESS_PATH, response_class=HTMLResponse)
def business_form(shell: ShellDep) -> HTMLResponse:
    business = load_business()
    return HTMLResponse(render_business_form(shell, business_form_values(business), first_run=business is None))


@router.post(BUSINESS_PATH, response_model=None)
def set_business(form: FormDep, shell: ShellDep) -> Response:
    try:
        save_business(parse_business_form(form))
    except ValidationError as e:
        first_run = load_business() is None
        html = render_business_form(shell, submitted_business_values(form), first_run, e.errors)
        return HTMLResponse(html, status_code=422)
    # 303 so the browser follows the form POST with a GET.
    return RedirectResponse("/", status_code=303)


def render_business_form(shell: Shell, values: dict[str, Any], first_run: bool, errors: list[str] | None = None) -> str:
    return templates.get_template("business.html").render(
        shell=shell, values=values, first_run=first_run, errors=errors or []
    )


_BUSINESS_FIELDS = ["name", "legalName", "address", "website", "email", "companyNumber", "registeredIn", "vatNumber"]


def business_form_values(business: Business | None = None) -> dict[str, Any]:
    """Values for the business form: the stored business, or blanks on the first run."""
    if business is None:
        return {}
    return {**business.model_dump(by_alias=True, exclude_none=True), "address": "\n".join(business.address)}


def submitted_business_values(body: FormBody) -> dict[str, Any]:
    """A business form submission as values for re-rendering it alongside its errors."""
    return {key: field(body, key) for key in _BUSINESS_FIELDS}


def parse_business_form(body: FormBody) -> Business:
    """Turns a business form submission into a valid Business, or raises ValidationError."""
    errors: list[str] = []
    required = {
        "name": "Trading name",
        "legalName": "Legal name",
        "email": "Email",
        "companyNumber": "Company number",
        "registeredIn": "Registered in",
    }
    for key, label in required.items():
        if not field(body, key):
            errors.append(f"{label} is required")
    if not lines(field(body, "address")):
        errors.append("Address is required")
    if errors:
        raise ValidationError("business", errors)

    business = {
        "name": field(body, "name"),
        "legalName": field(body, "legalName"),
        "address": lines(field(body, "address")),
        "website": field(body, "website") or None,
        "email": field(body, "email"),
        "companyNumber": field(body, "companyNumber"),
        "registeredIn": field(body, "registeredIn"),
        "vatNumber": field(body, "vatNumber") or None,
    }
    return validate_form(Business, business, "business")
