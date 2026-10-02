"""The shell on its own: an app of fake modules, with no invoicing."""

import re

import pytest
from fastapi.testclient import TestClient


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


def test_the_home_page_has_the_top_nav_with_nothing_marked(client: TestClient) -> None:
    page = client.get("/").text
    nav = re.findall(r'<a href="([^"]+)" >([^<]+)</a>', page)
    assert nav == [("/assets/", "Assets"), ("/savings/", "Savings"), ("/business", "Business")]
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
    assert '<a href="/savings/things"' in page
    assert '<a href="/assets/things"' not in page
    assert current_links(page) == [("/savings/", "true"), (page_link, "page")]


@pytest.mark.parametrize("path", ["/", "/savings/", "/savings/things/pot", "/business"])
def test_every_page_has_the_business_legal_name_in_its_header(client: TestClient, path: str) -> None:
    assert '<span class="label">Mackay Software Limited</span>' in client.get(path).text


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
    assert res.status_code == 200
    assert res.json() == {"count": 1}


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
