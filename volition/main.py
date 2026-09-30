"""HTTP server: GET / serves the invoice form, POST /invoice returns the PDF, /clients manages clients.

On the first run the pages redirect to ask for what invoices need: the supplier (/supplier), then the invoice
defaults (/defaults).
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import FormData

from volition import db
from volition.clients import create_client, delete_client, get_client, list_clients, update_client
from volition.config import ROOT, ValidationError, allowed_hosts
from volition.defaults import Defaults, load_defaults, save_defaults
from volition.form import (
    client_form_values,
    defaults_form_values,
    parse_client_form,
    parse_defaults_form,
    parse_invoice_form,
    parse_supplier_form,
    render_client_form,
    render_clients,
    render_defaults_form,
    render_form,
    render_supplier_form,
    submitted_client_values,
    submitted_defaults_values,
    submitted_supplier_values,
    supplier_form_values,
)
from volition.invoice import Supplier, parse_invoice_number
from volition.render import render_pdf
from volition.supplier import load_supplier, save_supplier

logger = logging.getLogger("volition")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on a database that can't be migrated rather than on the first request.
    db.migrate()
    yield


app = FastAPI(title="Volition", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
# Read once, at import: restart to change ALLOWED_HOSTS.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(), www_redirect=False)


class SetupIncomplete(Exception):
    """Something the first run asks for hasn't been saved yet; `path` is the page that asks for it."""

    def __init__(self, path: str) -> None:
        self.path = path


def require_supplier() -> Supplier:
    supplier = load_supplier()
    if supplier is None:
        raise SetupIncomplete("/supplier")
    return supplier


SupplierDep = Annotated[Supplier, Depends(require_supplier)]


def require_defaults(_: SupplierDep) -> Defaults:
    """Also requires the supplier, so the first run asks for that first."""
    defaults = load_defaults()
    if defaults is None:
        raise SetupIncomplete("/defaults")
    return defaults


DefaultsDep = Annotated[Defaults, Depends(require_defaults)]
#: For pages that don't use the defaults but shouldn't be reached before they're set.
NEEDS_DEFAULTS = [Depends(require_defaults)]


@app.get("/", response_class=HTMLResponse)
def invoice_form(defaults: DefaultsDep, supplier: SupplierDep) -> HTMLResponse:
    next_number = db.next_invoice_number(defaults.invoice_number_start)
    return HTMLResponse(render_form(defaults, supplier, next_number, list_clients()))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def form_data(request: Request) -> FormData:
    return await request.form()


FormDep = Annotated[FormData, Depends(form_data)]


# A plain `def`, so FastAPI runs it on a worker thread: rendering and file I/O block.
@app.post("/invoice")
def create_invoice(form: FormDep, supplier: SupplierDep) -> Response:
    invoice = parse_invoice_form(form, get_client)
    pdf = render_pdf(invoice, supplier)
    # Only count the number once the PDF actually exists.
    db.record_invoice_number(parse_invoice_number(invoice.number))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'},
    )


def _see_clients() -> RedirectResponse:
    # 303 so the browser follows a form POST with a GET.
    return RedirectResponse("/clients", status_code=303)


@app.get("/clients", response_class=HTMLResponse, dependencies=NEEDS_DEFAULTS)
def clients_page(supplier: SupplierDep) -> HTMLResponse:
    return HTMLResponse(render_clients(supplier, list_clients()))


@app.get("/clients/new", response_class=HTMLResponse, dependencies=NEEDS_DEFAULTS)
def new_client_form(supplier: SupplierDep) -> HTMLResponse:
    return HTMLResponse(render_client_form(supplier, client_form_values()))


@app.post("/clients", response_model=None)
def add_client(form: FormDep, supplier: SupplierDep) -> Response:
    try:
        create_client(parse_client_form(form))
    except ValidationError as e:
        html = render_client_form(supplier, submitted_client_values(form), errors=e.errors)
        return HTMLResponse(html, status_code=422)
    return _see_clients()


@app.get("/clients/{client_id}", response_class=HTMLResponse, dependencies=NEEDS_DEFAULTS)
def edit_client_form(client_id: str, supplier: SupplierDep) -> HTMLResponse:
    client = get_client(client_id)
    if client is None:
        raise HTTPException(404, "No such client")
    return HTMLResponse(render_client_form(supplier, client_form_values(client), client_id))


@app.post("/clients/{client_id}", response_model=None)
def save_client(client_id: str, form: FormDep, supplier: SupplierDep) -> Response:
    try:
        saved = update_client(client_id, parse_client_form(form))
    except ValidationError as e:
        html = render_client_form(supplier, submitted_client_values(form), client_id, e.errors)
        return HTMLResponse(html, status_code=422)
    if saved is None:
        raise HTTPException(404, "No such client")
    return _see_clients()


@app.post("/clients/{client_id}/delete")
def remove_client(client_id: str) -> RedirectResponse:
    if not delete_client(client_id):
        raise HTTPException(404, "No such client")
    return _see_clients()


@app.get("/defaults", response_class=HTMLResponse)
def defaults_form(supplier: SupplierDep) -> HTMLResponse:
    defaults = load_defaults()
    return HTMLResponse(render_defaults_form(supplier, defaults_form_values(defaults), first_run=defaults is None))


@app.post("/defaults", response_model=None)
def set_defaults(form: FormDep, supplier: SupplierDep) -> Response:
    try:
        save_defaults(parse_defaults_form(form))
    except ValidationError as e:
        first_run = load_defaults() is None
        html = render_defaults_form(supplier, submitted_defaults_values(form), first_run, e.errors)
        return HTMLResponse(html, status_code=422)
    return RedirectResponse("/", status_code=303)


@app.get("/supplier", response_class=HTMLResponse)
def supplier_form() -> HTMLResponse:
    supplier = load_supplier()
    return HTMLResponse(render_supplier_form(supplier, supplier_form_values(supplier), first_run=supplier is None))


@app.post("/supplier", response_model=None)
def set_supplier(form: FormDep) -> Response:
    try:
        save_supplier(parse_supplier_form(form))
    except ValidationError as e:
        supplier = load_supplier()
        html = render_supplier_form(supplier, submitted_supplier_values(form), supplier is None, e.errors)
        return HTMLResponse(html, status_code=422)
    # On the first run, / then redirects on to the defaults.
    return RedirectResponse("/", status_code=303)


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")


@app.exception_handler(SetupIncomplete)
def setup_incomplete(request: Request, exc: SetupIncomplete) -> RedirectResponse:
    return RedirectResponse(exc.path, status_code=303)


@app.exception_handler(ValidationError)
def validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse({"errors": exc.errors}, status_code=422)


type CallNext = Callable[[Request], Awaitable[Response]]


def _is_cross_origin(request: Request) -> bool:
    """Whether a browser sent this request from another site, e.g. a page posting a form to 127.0.0.1.

    Sec-Fetch-Site is trusted when present ("none" is the user typing the URL or using a bookmark).
    Otherwise Origin must match Host. Requests with neither come from curl, scripts or old browsers
    that wouldn't let a page forge them, so they are allowed.
    """
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site not in ("same-origin", "none")
    origin = request.headers.get("origin")
    if origin is None:
        return False
    return urlsplit(origin).netloc != request.headers.get("host")


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next: CallNext) -> Response:
    """Guards against CSRF: without it any website could post forms here, e.g. to change the bank details."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and _is_cross_origin(request):
        return JSONResponse({"errors": ["Cross-origin request rejected"]}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def unexpected_errors(request: Request, call_next: CallNext) -> Response:
    """Anything not already turned into a response (HTTPException, ValidationError) becomes a JSON 500."""
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"errors": [str(exc)]}, status_code=500)
