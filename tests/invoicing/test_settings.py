import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.invoicing.conftest import SETTINGS
from volition.core.models import Business
from volition.invoicing.models import BankDetails, InvoicingSettings, PresetLineItem
from volition.invoicing.store.settings import load_settings, save_settings


@pytest.fixture
def first_run(app: FastAPI, business: Business) -> Iterator[TestClient]:
    """An app whose database has the business but no invoicing settings yet."""
    with TestClient(app, base_url="http://localhost") as c:
        yield c


SETTINGS_FORM: dict[str, str | list[str]] = {
    "invoiceNumberStart": "12",
    "unit": "hours",
    "description": ["Consultancy", "", "Travel"],
    "detail": ["Remote", "", ""],
    "rate": ["80", "", ""],
    "notes": "Thanks",
    "paymentTermsDays": "14",
    "bankName": "Monzo",
    "accountName": "Acme Ltd",
    "sortCode": "12 34 56",
    "accountNumber": "1234 5678",
}


def test_settings_round_trip_and_are_none_until_saved() -> None:
    assert load_settings() is None
    save_settings(SETTINGS)
    assert load_settings() == SETTINGS
    save_settings(SETTINGS.model_copy(update={"notes": "later", "payment_terms_days": 7}))
    settings = load_settings()
    assert settings is not None
    assert (settings.notes, settings.payment_terms_days) == ("later", 7)


@pytest.mark.parametrize(
    "path", ["/invoicing/", "/invoicing/clients", "/invoicing/clients/new", "/invoicing/clients/anything"]
)
def test_pages_redirect_to_the_settings_form_on_the_first_run(first_run: TestClient, path: str) -> None:
    res = first_run.get(path, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/invoicing/settings"


@pytest.mark.parametrize("path", ["/invoicing/invoice", "/invoicing/clients"])
def test_posts_redirect_to_the_settings_form_on_the_first_run(first_run: TestClient, path: str) -> None:
    res = first_run.post(path, data={"name": "x"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/invoicing/settings"


def test_the_first_run_form_suggests_starting_values(first_run: TestClient) -> None:
    page = first_run.get("/invoicing/settings").text
    assert "Before the first invoice" in page
    assert "Save and continue" in page
    assert "Cancel" not in page
    assert 'name="invoiceNumberStart" type="number" min="1" step="1" required value="1"' in page
    assert '<option value="days" selected>Days</option>' in page
    assert 'name="vat" type="checkbox" checked' in page
    assert 'name="paymentTermsDays" type="number" min="0" step="1" required value="30"' in page


def test_saving_the_settings_continues_to_the_invoice_form(first_run: TestClient) -> None:
    res = first_run.post("/invoicing/settings", data=SETTINGS_FORM, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/invoicing/"
    assert load_settings() == InvoicingSettings(
        invoice_number_start=12,
        vat=False,  # unticked, so absent from the submission
        unit="hours",
        line_items=[
            PresetLineItem(description="Consultancy", detail="Remote", rate=80),
            PresetLineItem(description="Travel"),
        ],
        notes="Thanks",
        payment_terms_days=14,
        bank=BankDetails(bank_name="Monzo", account_name="Acme Ltd", sort_code="12-34-56", account_number="12345678"),
    )
    page = first_run.get("/invoicing/").text
    assert "Next in sequence: MS-0012" in page
    assert "Blank = issue date + 14 days" in page


def test_an_invalid_settings_form_is_re_rendered_with_its_errors_and_values(first_run: TestClient) -> None:
    body = {
        **SETTINGS_FORM,
        "invoiceNumberStart": "0",
        "description": ["", "", "Travel"],
        "rate": ["80", "", "-1"],
        "paymentTermsDays": "-1",
        "bankName": "",
        "sortCode": "12-34",
    }
    res = first_run.post("/invoicing/settings", data=body)
    assert res.status_code == 422
    assert re.findall(r"<li>(.*?)</li>", res.text) == [
        "First invoice number must be a whole number of 1 or more",
        "Line 1: description is required",
        "Line 2: rate must be a whole number of 0 or more",
        "Payment terms must be a whole number of 0 or more",
        "Bank is required",
        "Sort code must be 6 digits",
    ]
    for value in ["Remote", "Acme Ltd", "12-34", "1234 5678", "-1"]:
        assert f'value="{value}"' in res.text
    assert "Save and continue" in res.text
    assert load_settings() is None


def test_an_account_number_needs_8_digits(first_run: TestClient) -> None:
    res = first_run.post("/invoicing/settings", data={**SETTINGS_FORM, "accountNumber": "1234 567"})
    assert res.status_code == 422
    assert re.findall(r"<li>(.*?)</li>", res.text) == ["Account number must be 8 digits"]
    assert load_settings() is None


def test_schema_errors_on_the_settings_form_are_reported(first_run: TestClient) -> None:
    res = first_run.post("/invoicing/settings", data={**SETTINGS_FORM, "unit": "weeks"})
    assert res.status_code == 422
    assert re.findall(r"<li>(/\w+) ", res.text) == ["/unit"]


def test_editing_the_saved_settings(client: TestClient) -> None:
    page = client.get("/invoicing/settings").text
    assert "Before the first invoice" not in page
    assert '<a href="/invoicing/">Cancel</a>' in page
    assert 'value="IT &amp; Software Consultancy Services"' in page
    assert f'value="{SETTINGS.bank.sort_code}"' in page
    assert 'value="Monzo"' in page
    res = client.post("/invoicing/settings", data={**SETTINGS_FORM, "vat": "on"}, follow_redirects=False)
    assert res.status_code == 303
    settings = load_settings()
    assert settings is not None
    assert settings.vat is True
    assert settings.bank.account_number == "12345678"
