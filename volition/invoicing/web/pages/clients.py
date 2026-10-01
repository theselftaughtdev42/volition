"""The client list (/invoicing/clients) and the form that adds and edits clients."""

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from volition.core.errors import ValidationError
from volition.core.web.deps import FormDep
from volition.core.web.forms import FormBody, field, lines, validate_form
from volition.core.web.shell import Shell, ShellDep
from volition.invoicing.invoices import VAT_PERCENT
from volition.invoicing.models import ClientDetails, ClientRecord
from volition.invoicing.store.clients import create_client, delete_client, get_client, list_clients, update_client
from volition.invoicing.web.forms import parse_preset_lines, submitted_preset_lines
from volition.invoicing.web.pages import PREFIX, render_page

router = APIRouter()


def _see_clients() -> RedirectResponse:
    # 303 so the browser follows a form POST with a GET.
    return RedirectResponse(f"{PREFIX}/clients", status_code=303)


@router.get("/clients", response_class=HTMLResponse)
def clients_page(shell: ShellDep) -> HTMLResponse:
    return HTMLResponse(render_clients(shell, list_clients()))


@router.get("/clients/new", response_class=HTMLResponse)
def new_client_form(shell: ShellDep) -> HTMLResponse:
    return HTMLResponse(render_client_form(shell, client_form_values()))


@router.post("/clients", response_model=None)
def add_client(form: FormDep, shell: ShellDep) -> Response:
    try:
        create_client(parse_client_form(form))
    except ValidationError as e:
        html = render_client_form(shell, submitted_client_values(form), errors=e.errors)
        return HTMLResponse(html, status_code=422)
    return _see_clients()


@router.get("/clients/{client_id}", response_class=HTMLResponse)
def edit_client_form(client_id: str, shell: ShellDep) -> HTMLResponse:
    client = get_client(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    return HTMLResponse(render_client_form(shell, client_form_values(client), client_id))


@router.post("/clients/{client_id}", response_model=None)
def save_client(client_id: str, form: FormDep, shell: ShellDep) -> Response:
    try:
        saved = update_client(client_id, parse_client_form(form))
    except ValidationError as e:
        html = render_client_form(shell, submitted_client_values(form), client_id, e.errors)
        return HTMLResponse(html, status_code=422)
    if saved is None:
        raise HTTPException(404, "No such client")
    return _see_clients()


@router.post("/clients/{client_id}/delete")
def remove_client(client_id: str) -> RedirectResponse:
    if not delete_client(client_id):
        raise HTTPException(404, "No such client")
    return _see_clients()


def render_clients(shell: Shell, clients: list[ClientRecord]) -> str:
    return render_page(
        "clients.html",
        shell,
        clients=[client.model_dump(by_alias=True, exclude_none=True) for client in clients],
    )


def render_client_form(
    shell: Shell,
    values: dict[str, Any],
    client_id: str | None = None,
    errors: list[str] | None = None,
) -> str:
    return render_page(
        "client.html",
        shell,
        vatPercent=VAT_PERCENT,
        values=values,
        client_id=client_id,
        errors=errors or [],
    )


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


def submitted_client_values(body: FormBody) -> dict[str, Any]:
    """A client form submission as values for re-rendering it, e.g. alongside its errors."""
    return {
        **{key: field(body, key) for key in ["name", "contact", "email", "address", "vat", "unit", "notes"]},
        "lineItems": submitted_preset_lines(body),
    }


def parse_client_form(body: FormBody) -> ClientDetails:
    """Turns a client form submission into valid ClientDetails, or raises ValidationError."""
    errors: list[str] = []
    if not field(body, "name"):
        errors.append("Name is required")
    if not lines(field(body, "address")):
        errors.append("Address is required")
    line_items = parse_preset_lines(body, errors)
    if errors:
        raise ValidationError("client", errors)

    vat = field(body, "vat")
    client = {
        "name": field(body, "name"),
        "contact": field(body, "contact") or None,
        "address": lines(field(body, "address")),
        "email": field(body, "email") or None,
        "vat": {"yes": True, "no": False}.get(vat, vat or None),
        "unit": field(body, "unit") or None,
        "lineItems": line_items,
        "notes": field(body, "notes") or None,
    }
    return validate_form(ClientDetails, client, "client")
