"""The FastAPI app: the pages in `volition.web.pages`, plus the middleware and error handling they share.

GET / serves the invoice form, POST /invoice returns the PDF, /clients manages clients. On the first run the
pages redirect to ask for what invoices need: the supplier (/supplier), then the invoice defaults (/defaults).
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from volition.config import ROOT, allowed_hosts
from volition.errors import ValidationError
from volition.store import db
from volition.web.deps import SetupIncomplete
from volition.web.pages import clients, defaults, invoice, supplier

logger = logging.getLogger("volition")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on a database that can't be migrated rather than on the first request.
    db.migrate()
    yield


app = FastAPI(title="Volition", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
# Read once, at import: restart to change ALLOWED_HOSTS.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(), www_redirect=False)

for page in (invoice, clients, defaults, supplier):
    app.include_router(page.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
