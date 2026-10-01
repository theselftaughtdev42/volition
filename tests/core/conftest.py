"""The shell's test app: fake modules, with no invoicing."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from tests.conftest import BUSINESS
from volition.core.app import create_app
from volition.core.modules import Module, NavLink
from volition.core.store.business import save_business
from volition.core.templates import environment
from volition.core.web.shell import ShellDep

TEMPLATES = Path(__file__).resolve().parent / "fake_templates"


def fake_module(slug: str, title: str, migrations: tuple[str, ...] = ()) -> Module:
    """A module with a home page, a list of things (one of them broken) and a form that adds to it."""
    templates = environment({slug: TEMPLATES})
    router = APIRouter()
    things: list[str] = []

    def page(shell: ShellDep, message: str) -> HTMLResponse:
        return HTMLResponse(templates.get_template(f"{slug}/page.html").render(shell=shell, message=message))

    @router.get("/", response_class=HTMLResponse)
    def home(shell: ShellDep) -> HTMLResponse:
        return page(shell, f"{title} home")

    @router.get("/things", response_class=HTMLResponse)
    def list_things(shell: ShellDep) -> HTMLResponse:
        return page(shell, ", ".join(things))

    @router.get("/things/broken")
    def broken() -> None:
        raise RuntimeError("database is locked")

    @router.get("/things/{name}", response_class=HTMLResponse)
    def thing(name: str, shell: ShellDep) -> HTMLResponse:
        return page(shell, name)

    @router.post("/things")
    def add_thing() -> dict[str, int]:
        things.append("thing")
        return {"count": len(things)}

    return Module(
        slug=slug,
        title=title,
        description=f"Keeps track of {slug}.",
        router=router,
        nav=(NavLink("Home", "/"), NavLink("Things", "/things")),
        migrations=migrations,
        templates=TEMPLATES,
    )


@pytest.fixture
def app() -> FastAPI:
    return create_app([fake_module("assets", "Assets"), fake_module("savings", "Savings")])


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """With the business saved, but nothing any module might ask for."""
    with TestClient(app, base_url="http://localhost") as c:
        save_business(BUSINESS)
        yield c
