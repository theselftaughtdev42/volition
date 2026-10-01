"""The shell on its own: an app of fake modules, with no invoicing."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from volition.core.app import create_app
from volition.core.modules import Module, NavLink
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
    with TestClient(app, base_url="http://localhost") as c:
        yield c


def current_links(page: str) -> list[tuple[str, str]]:
    """(href, aria-current) for every marked link."""
    return re.findall(r'<a href="([^"]+)" aria-current="(\w+)">', page)


def test_the_home_page_has_a_card_per_module(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    cards = re.findall(r'<a class="card" href="([^"]+)">\s*<h2>([^<]+)</h2>\s*<p>([^<]+)</p>', res.text)
    assert cards == [
        ("/assets/", "Assets", "Keeps track of assets."),
        ("/savings/", "Savings", "Keeps track of savings."),
    ]


def test_the_home_page_has_the_module_nav_with_nothing_marked(client: TestClient) -> None:
    page = client.get("/").text
    assert '<a href="/assets/" >Assets</a>' in page and '<a href="/savings/" >Savings</a>' in page
    assert '<nav class="pages"' not in page
    assert current_links(page) == []


@pytest.mark.parametrize(
    ("path", "page_link"),
    [
        ("/savings/", "/savings/"),
        ("/savings/things", "/savings/things"),
        ("/savings/things/pot", "/savings/things"),
    ],
)
def test_module_pages_mark_their_module_and_page(client: TestClient, path: str, page_link: str) -> None:
    page = client.get(path).text
    assert '<a href="/assets/" >Assets</a>' in page
    assert '<nav class="pages" aria-label="Savings">' in page
    assert '<a href="/savings/things"' in page and '<a href="/assets/things"' not in page
    assert current_links(page) == [("/savings/", "true"), (page_link, "page")]


def test_modules_are_mounted_under_their_slug(client: TestClient) -> None:
    assert "Assets home" in client.get("/assets/").text
    assert client.get("/things").status_code == 404


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_assets_are_served(client: TestClient) -> None:
    """/assets is the shell's static files, even alongside a module of the same name."""
    res = client.get("/assets/ms-mark.svg")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/svg+xml")


def test_unexpected_errors_are_json_500s(client: TestClient) -> None:
    res = client.get("/savings/things/broken")
    assert res.status_code == 500
    assert res.json() == {"errors": ["database is locked"]}


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        # Sec-Fetch-Site wins over a matching Origin.
        {"Sec-Fetch-Site": "cross-site", "Origin": "http://localhost"},
    ],
)
def test_cross_origin_posts_to_modules_are_rejected(client: TestClient, headers: dict[str, str]) -> None:
    res = client.post("/savings/things", headers=headers)
    assert res.status_code == 403
    assert res.json() == {"errors": ["Cross-origin request rejected"]}
    assert client.post("/savings/things").json() == {"count": 1}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}, {"Origin": "http://localhost"}],
)
def test_same_origin_and_non_browser_posts_are_allowed(client: TestClient, headers: dict[str, str]) -> None:
    res = client.post("/savings/things", headers=headers)
    assert res.status_code == 200 and res.json() == {"count": 1}


def test_cross_origin_gets_are_allowed(client: TestClient) -> None:
    assert client.get("/savings/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1:3000", "[::1]:3000"])
def test_local_hosts_are_allowed(client: TestClient, host: str) -> None:
    assert client.get("/health", headers={"Host": host}).status_code == 200


def test_other_hosts_are_rejected(client: TestClient) -> None:
    """A DNS-rebound page is same-origin to the browser, so only the Host header gives it away."""
    headers = {"Host": "evil.example:3000", "Sec-Fetch-Site": "same-origin", "Origin": "http://evil.example:3000"}
    assert client.get("/", headers=headers).status_code == 400
    assert client.get("/savings/", headers=headers).status_code == 400
    assert client.post("/savings/things", headers=headers).status_code == 400
    assert client.post("/savings/things").json() == {"count": 1}
