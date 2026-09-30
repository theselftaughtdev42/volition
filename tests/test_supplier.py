import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SUPPLIER
from volition.invoice import BankDetails, Supplier
from volition.main import app
from volition.supplier import load_supplier, save_supplier


@pytest.fixture
def first_run() -> Iterator[TestClient]:
    """An app whose database is empty."""
    with TestClient(app, base_url="http://localhost") as c:
        yield c


SUPPLIER_FORM = {
    "name": "Acme",
    "legalName": "Acme Ltd",
    "address": "1 High St\n\n  Leeds  \n",
    "website": "",
    "email": "hello@acme.co.uk",
    "companyNumber": "123",
    "registeredIn": "England & Wales",
    "vatNumber": "",
    "paymentTermsDays": "14",
    "accountName": "Acme Ltd",
    "sortCode": "12 34 56",
    "accountNumber": "1234 5678",
}


def test_supplier_round_trips_and_is_none_until_saved() -> None:
    assert load_supplier() is None
    save_supplier(SUPPLIER)
    assert load_supplier() == SUPPLIER
    save_supplier(SUPPLIER.model_copy(update={"payment_terms_days": 7}))
    assert load_supplier().payment_terms_days == 7  # type: ignore[union-attr]


@pytest.mark.parametrize("path", ["/", "/clients", "/clients/new", "/defaults"])
def test_pages_redirect_to_the_supplier_form_on_the_first_run(first_run: TestClient, path: str) -> None:
    res = first_run.get(path, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/supplier"


def test_the_first_run_form_suggests_starting_values(first_run: TestClient) -> None:
    page = first_run.get("/supplier").text
    assert "Welcome." in page and "Save and continue" in page and "Cancel" not in page
    assert 'name="paymentTermsDays" type="number" min="0" step="1" required value="30"' in page


def test_saving_the_supplier_continues_to_the_defaults(first_run: TestClient) -> None:
    res = first_run.post("/supplier", data=SUPPLIER_FORM)
    assert res.url.path == "/defaults" and "Next, set the defaults" in res.text
    assert "Acme Ltd" in res.text  # in the header
    assert load_supplier() == Supplier(
        name="Acme",
        legal_name="Acme Ltd",
        address=["1 High St", "Leeds"],
        email="hello@acme.co.uk",
        company_number="123",
        registered_in="England & Wales",
        payment_terms_days=14,
        bank=BankDetails(account_name="Acme Ltd", sort_code="12-34-56", account_number="12345678"),
    )


def test_an_invalid_supplier_form_is_re_rendered_with_its_errors_and_values(first_run: TestClient) -> None:
    body = {**SUPPLIER_FORM, "legalName": "", "address": " ", "paymentTermsDays": "-1", "sortCode": "12-34"}
    res = first_run.post("/supplier", data=body)
    assert res.status_code == 422
    assert re.findall(r"<li>(.*?)</li>", res.text) == [
        "Legal name is required",
        "Address is required",
        "Payment terms must be a whole number of 0 or more",
        "Sort code must be 6 digits",
    ]
    assert 'value="hello@acme.co.uk"' in res.text and "Save and continue" in res.text
    assert load_supplier() is None


def test_schema_errors_on_the_supplier_form_are_reported(first_run: TestClient) -> None:
    res = first_run.post("/supplier", data={**SUPPLIER_FORM, "email": "not an email"})
    assert res.status_code == 422
    assert re.findall(r"<li>(/\w+) ", res.text) == ["/email"]


def test_editing_the_saved_supplier(client: TestClient) -> None:
    page = client.get("/supplier").text
    assert "Welcome." not in page and '<a href="/">Cancel</a>' in page
    assert f'value="{SUPPLIER.bank.sort_code}"' in page and "Mansion House, Manchester Rd\n" in page
    res = client.post("/supplier", data={**SUPPLIER_FORM, "vatNumber": "GB 1"}, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert load_supplier().vat_number == "GB 1"  # type: ignore[union-attr]
    assert "Blank = issue date + 14 days" in client.get("/").text
