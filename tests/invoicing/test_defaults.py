import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from volition.invoicing.models import Defaults, PresetLineItem, Supplier
from volition.invoicing.store.defaults import load_defaults, save_defaults


@pytest.fixture
def first_run(app: FastAPI, supplier: Supplier) -> Iterator[TestClient]:
    """An app whose database has the supplier but no defaults yet."""
    with TestClient(app, base_url="http://localhost") as c:
        yield c


DEFAULTS_FORM: dict[str, str | list[str]] = {
    "invoiceNumberStart": "12",
    "unit": "hours",
    "description": ["Consultancy", "", "Travel"],
    "detail": ["Remote", "", ""],
    "rate": ["80", "", ""],
    "notes": "Thanks",
}


def test_defaults_round_trip_and_are_none_until_saved() -> None:
    assert load_defaults() is None
    defaults = Defaults(invoice_number_start=5, vat=False, unit="items", line_items=[PresetLineItem(description="x")])
    save_defaults(defaults)
    assert load_defaults() == defaults
    save_defaults(defaults.model_copy(update={"notes": "later"}))
    assert load_defaults().notes == "later"  # type: ignore[union-attr]


@pytest.mark.parametrize("path", ["/", "/clients", "/clients/new", "/clients/anything"])
def test_pages_redirect_to_the_defaults_form_on_the_first_run(first_run: TestClient, path: str) -> None:
    res = first_run.get(path, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/defaults"


def test_the_first_run_form_suggests_starting_values(first_run: TestClient) -> None:
    page = first_run.get("/defaults").text
    assert "Next, set the defaults" in page and "Save and continue" in page and "Cancel" not in page
    assert 'name="invoiceNumberStart" type="number" min="1" step="1" required value="1"' in page
    assert '<option value="days" selected>Days</option>' in page
    assert 'name="vat" type="checkbox" checked' in page


def test_saving_the_defaults_continues_to_the_invoice_form(first_run: TestClient) -> None:
    res = first_run.post("/defaults", data=DEFAULTS_FORM, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert load_defaults() == Defaults(
        invoice_number_start=12,
        vat=False,  # unticked, so absent from the submission
        unit="hours",
        line_items=[
            PresetLineItem(description="Consultancy", detail="Remote", rate=80),
            PresetLineItem(description="Travel"),
        ],
        notes="Thanks",
    )
    page = first_run.get("/").text
    assert "Next in sequence: MS-0012" in page


def test_an_invalid_defaults_form_is_re_rendered_with_its_errors_and_values(first_run: TestClient) -> None:
    body = {**DEFAULTS_FORM, "invoiceNumberStart": "0", "description": ["", "", "Travel"], "rate": ["80", "", "-1"]}
    res = first_run.post("/defaults", data=body)
    assert res.status_code == 422
    assert re.findall(r"<li>(.*?)</li>", res.text) == [
        "First invoice number must be a whole number of 1 or more",
        "Line 1: description is required",
        "Line 2: rate must be a whole number of 0 or more",
    ]
    assert 'value="Remote"' in res.text and "Save and continue" in res.text
    assert load_defaults() is None


def test_schema_errors_on_the_defaults_form_are_reported(first_run: TestClient) -> None:
    res = first_run.post("/defaults", data={**DEFAULTS_FORM, "unit": "weeks"})
    assert res.status_code == 422
    assert re.findall(r"<li>(/\w+) ", res.text) == ["/unit"]


def test_editing_the_saved_defaults(client: TestClient, defaults: Defaults) -> None:
    page = client.get("/defaults").text
    assert "Next, set the defaults" not in page and '<a href="/">Cancel</a>' in page
    assert 'value="IT &amp; Software Consultancy Services"' in page
    res = client.post("/defaults", data={**DEFAULTS_FORM, "vat": "on"}, follow_redirects=False)
    assert res.status_code == 303
    assert load_defaults().vat is True  # type: ignore[union-attr]
