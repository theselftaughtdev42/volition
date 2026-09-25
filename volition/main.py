"""HTTP server: GET / serves the invoice form, POST /invoice returns the PDF."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import FormData

from volition.config import (
    ROOT,
    Defaults,
    ValidationError,
    load_defaults,
    load_supplier,
    next_invoice_number,
    record_invoice_number,
)
from volition.form import parse_invoice_form, render_form
from volition.invoice import Supplier, parse_invoice_number
from volition.render import render_pdf

logger = logging.getLogger("volition")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on missing or invalid config rather than on the first request.
    load_supplier()
    load_defaults()
    yield


app = FastAPI(title="Volition", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

DefaultsDep = Annotated[Defaults, Depends(load_defaults)]
SupplierDep = Annotated[Supplier, Depends(load_supplier)]


@app.get("/", response_class=HTMLResponse)
def invoice_form(defaults: DefaultsDep, supplier: SupplierDep) -> HTMLResponse:
    return HTMLResponse(render_form(defaults, supplier, next_invoice_number(defaults)))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def form_data(request: Request) -> FormData:
    return await request.form()


# A plain `def`, so FastAPI runs it on a worker thread: rendering and file I/O block.
@app.post("/invoice")
def create_invoice(form: Annotated[FormData, Depends(form_data)], supplier: SupplierDep) -> Response:
    invoice = parse_invoice_form(form)
    pdf = render_pdf(invoice, supplier)
    # Only count the number once the PDF actually exists.
    record_invoice_number(parse_invoice_number(invoice.number))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'},
    )


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")


@app.exception_handler(ValidationError)
def validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse({"errors": exc.errors}, status_code=422)


type CallNext = Callable[[Request], Awaitable[Response]]


@app.middleware("http")
async def unexpected_errors(request: Request, call_next: CallNext) -> Response:
    """Anything not already turned into a response (HTTPException, ValidationError) becomes a JSON 500."""
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"errors": [str(exc)]}, status_code=500)
