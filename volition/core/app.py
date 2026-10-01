"""The app factory: builds the FastAPI app from a list of modules, with the middleware and error handling they share.

Each module's router is mounted at `/<slug>`, and the home page at `/` links to every module. A dependency raising
`SetupIncomplete` redirects to the page that asks for what is missing, so modules own their first-run setup.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from volition.core.config import ROOT, allowed_hosts
from volition.core.errors import ValidationError
from volition.core.modules import Module
from volition.core.store import db
from volition.core.templates import environment
from volition.core.web.deps import SetupIncomplete
from volition.core.web.shell import ShellDep, module_href

templates = environment({})

logger = logging.getLogger("volition")

type CallNext = Callable[[Request], Awaitable[Response]]


def create_app(modules: Sequence[Module], bootstrap: db.Bootstrap | None = None) -> FastAPI:
    """`bootstrap` upgrades a database from before modules, if there might be one."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fail fast on a database that can't be migrated rather than on the first request.
        db.migrate(modules, bootstrap)
        yield

    app = FastAPI(title="Volition", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Read once, when the app is built: restart to change ALLOWED_HOSTS.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(), www_redirect=False)

    # What the shell dependency builds every page's nav from.
    app.state.modules = tuple(modules)
    for module in modules:
        app.include_router(module.router, prefix=f"/{module.slug}")

    @app.get("/", response_class=HTMLResponse)
    def home(shell: ShellDep) -> HTMLResponse:
        cards = [{"title": m.title, "description": m.description, "href": module_href(m)} for m in modules]
        return HTMLResponse(templates.get_template("home.html").render(shell=shell, cards=cards))

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

    @app.middleware("http")
    async def reject_cross_origin_writes(request: Request, call_next: CallNext) -> Response:
        """Guards against CSRF: without it any website could post forms here, e.g. to change saved settings."""
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

    return app


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
