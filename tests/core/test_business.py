"""The business: the shell's only first-run requirement, entered and edited on /business."""

import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import BUSINESS
from volition.core.models import Business
from volition.core.store.business import load_business


@pytest.fixture
def first_run(app: FastAPI) -> Iterator[TestClient]:
    """An app whose database is empty."""
    with TestClient(app, base_url="http://localhost") as c:
        yield c


BUSINESS_FORM = {
    "name": "Acme",
    "legalName": "Acme Ltd",
    "address": "1 High St\n\n  Leeds  \n",
    "website": "",
    "email": "hello@acme.co.uk",
    "companyNumber": "123",
    "registeredIn": "England & Wales",
    "vatNumber": "",
}


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/"), ("GET", "/savings/"), ("GET", "/savings/things/pot"), ("POST", "/savings/things")],
)
def test_every_page_redirects_to_the_business_form_on_the_first_run(
    first_run: TestClient, method: str, path: str
) -> None:
    res = first_run.request(method, path, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/business"


def test_health_and_assets_dont_need_the_business(first_run: TestClient) -> None:
    assert first_run.get("/health").status_code == 200
    assert first_run.get("/assets/ms-mark.svg").status_code == 200


def test_the_first_run_form_asks_for_the_business(first_run: TestClient) -> None:
    res = first_run.get("/business")
    assert res.status_code == 200
    assert "Welcome." in res.text and "Save and continue" in res.text and "Cancel" not in res.text
    assert '<form id="business" method="post" action="/business">' in res.text
    assert '<span class="label">' not in res.text.split("</header>")[0]  # no legal name yet


def test_saving_the_business_opens_the_app(first_run: TestClient) -> None:
    res = first_run.post("/business", data=BUSINESS_FORM, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert load_business() == Business(
        name="Acme",
        legal_name="Acme Ltd",
        address=["1 High St", "Leeds"],
        email="hello@acme.co.uk",
        company_number="123",
        registered_in="England & Wales",
    )
    # Modules that need nothing more are usable straight away.
    page = first_run.get("/savings/things/pot").text
    assert "<p>pot</p>" in page and '<span class="label">Acme Ltd</span>' in page
    assert first_run.post("/savings/things").json() == {"count": 1}


def test_an_invalid_business_form_is_re_rendered_with_its_errors_and_values(first_run: TestClient) -> None:
    body = {**BUSINESS_FORM, "legalName": "", "registeredIn": "", "address": " "}
    res = first_run.post("/business", data=body)
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("text/html")
    assert re.findall(r"<li>(.*?)</li>", res.text) == [
        "Legal name is required",
        "Registered in is required",
        "Address is required",
    ]
    assert 'value="hello@acme.co.uk"' in res.text and 'value="123"' in res.text and "Save and continue" in res.text
    assert load_business() is None


def test_schema_errors_on_the_business_form_are_reported(first_run: TestClient) -> None:
    res = first_run.post("/business", data={**BUSINESS_FORM, "email": "not an email"})
    assert res.status_code == 422
    assert re.findall(r"<li>(/\w+) ", res.text) == ["/email"]
    assert 'value="not an email"' in res.text


def test_editing_the_saved_business(client: TestClient) -> None:
    page = client.get("/business").text
    assert "Welcome." not in page and '<a href="/">Cancel</a>' in page
    assert f'value="{BUSINESS.vat_number}"' in page and "Mansion House, Manchester Rd\n" in page
    res = client.post("/business", data={**BUSINESS_FORM, "vatNumber": "GB 1"}, follow_redirects=False)
    assert res.status_code == 303
    assert load_business().vat_number == "GB 1"  # type: ignore[union-attr]
    assert '<span class="label">Acme Ltd</span>' in client.get("/").text


def test_an_invalid_edit_keeps_the_saved_business(client: TestClient) -> None:
    res = client.post("/business", data={**BUSINESS_FORM, "name": ""})
    assert res.status_code == 422
    assert "Trading name is required" in res.text and "Save and continue" not in res.text
    assert load_business() == BUSINESS


def test_the_business_page_marks_business_in_the_nav(client: TestClient) -> None:
    page = client.get("/business").text
    assert re.findall(r'<a href="([^"]+)" aria-current="(\w+)">', page) == [("/business", "true")]
    assert '<nav class="pages"' not in page
