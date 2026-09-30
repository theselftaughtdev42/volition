import json
import re
from dataclasses import dataclass
from io import BytesIO

import pytest
from pypdf import PdfReader
from fastapi.testclient import TestClient
from starlette.datastructures import FormData

from volition.clients import ClientDetails, ClientRecord, create_client
from volition.config import ValidationError, allowed_hosts, validate_invoice
from volition.db import next_invoice_number, record_invoice_number
from volition.form import parse_invoice_form
from volition.invoice import Invoice, LineItem, Supplier
from volition.render import render_html, render_pdf
from volition.supplier import load_supplier


def test_invoice_numbers_start_from_the_configured_int_and_only_move_forward() -> None:
    assert next_invoice_number(42) == 42
    record_invoice_number(42)
    assert next_invoice_number(42) == 43
    record_invoice_number(10)  # regenerating an old invoice
    assert next_invoice_number(42) == 43
    assert next_invoice_number(100) == 100


FORM_BODY: dict[str, str | list[str]] = {
    "number": "42",
    "issueDate": "2026-09-19",
    "dueDate": "",
    "periodStart": "2026-09-01",
    "periodEnd": "2026-09-30",
    "vat": "on",
    "unit": "days",
    "clientId": "c1",
    "description": ["Backend development", "", "Code review"],
    "detail": ["Sprint 14", "", ""],
    "quantity": ["10", "", "1"],
    "rate": ["550", "550", "825"],
    "notes": "",
}


def form_items(body: dict[str, str | list[str]]) -> list[tuple[str, str]]:
    return [(k, v) for k, vs in body.items() for v in (vs if isinstance(vs, list) else [vs])]


def form(body: dict[str, str | list[str]]) -> FormData:
    return FormData(form_items(body))


EXAMPLE_CLIENT = ClientDetails(name="Example Client Ltd", address=["1 Example Street", "London, EC1A 1AA"])
CLIENTS = {"c1": ClientRecord(id="c1", **dict(EXAMPLE_CLIENT))}


def parse(body: dict[str, str | list[str]]) -> Invoice:
    return parse_invoice_form(form(body), CLIENTS.get)


def test_form_submission_parses_into_a_valid_invoice_skipping_blank_rows() -> None:
    invoice = parse(FORM_BODY)
    assert invoice.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "number": "MS-0042",
        "issueDate": "2026-09-19",
        "period": {"start": "2026-09-01", "end": "2026-09-30"},
        "vat": True,
        "unit": "days",
        "client": {"name": "Example Client Ltd", "address": ["1 Example Street", "London, EC1A 1AA"]},
        "lineItems": [
            {"description": "Backend development", "detail": "Sprint 14", "quantity": 10, "rate": 550},
            {"description": "Code review", "quantity": 1, "rate": 825},
        ],
    }


def test_an_unticked_vat_box_is_absent_from_the_submission_and_means_no_vat() -> None:
    without_vat = {k: v for k, v in FORM_BODY.items() if k != "vat"}
    assert parse(without_vat).vat is False


def test_form_errors_are_reported_together() -> None:
    body = {
        **FORM_BODY,
        "clientId": "",
        "quantity": ["", "", "1.5"],
        "rate": ["550", "550", "-1"],
        "periodEnd": "2026-08-01",
    }
    with pytest.raises(ValidationError) as exc:
        parse(body)
    assert exc.value.errors == [
        "Line 1: quantity must be a whole number of 1 or more",
        "Line 2: quantity must be a whole number of 1 or more",
        "Line 2: rate must be a whole number of 0 or more",
        "Period start must be on or before its end",
        "Choose a client",
    ]


def test_an_unknown_client_is_an_error() -> None:
    with pytest.raises(ValidationError) as exc:
        parse({**FORM_BODY, "clientId": "deleted"})
    assert exc.value.errors == ["That client no longer exists; reload the page"]


def test_schema_errors_are_reported_with_their_location() -> None:
    with pytest.raises(ValidationError) as exc:
        parse({**FORM_BODY, "unit": "weeks"})
    assert [e.split(" ")[0] for e in exc.value.errors] == ["/unit"]


def test_the_notes_section_only_appears_when_notes_are_given(invoice: Invoice, supplier: Supplier) -> None:
    assert not re.search(r">Notes<", render_html(invoice, supplier))
    html = render_html(invoice.model_copy(update={"notes": "Paid in advance"}), supplier)
    assert re.search(r">Notes<[\s\S]*Paid in advance", html)


@dataclass
class PdfInfo:
    pages: int
    fonts: list[str]
    images: int
    size: tuple[float, float]


def inspect_pdf(pdf: bytes) -> PdfInfo:
    """Page count, font names (subset prefix dropped), image count and first-page size in points."""
    reader = PdfReader(BytesIO(pdf))
    fonts: set[str] = set()
    images = 0
    for page in reader.pages:
        resources = page.get("/Resources", {})
        for font in resources.get("/Font", {}).values():
            fonts.add(re.sub(r"^[A-Z]{6}\+", "", str(font.get_object()["/BaseFont"]).lstrip("/")))
        for xobject in resources.get("/XObject", {}).values():
            images += xobject.get_object().get("/Subtype") == "/Image"
    box = reader.pages[0].mediabox
    return PdfInfo(len(reader.pages), sorted(fonts), images, (float(box.width), float(box.height)))


def test_example_invoice_renders_to_one_a4_page_with_embedded_jetbrains_mono_and_a_vector_logo(
    invoice: Invoice, supplier: Supplier
) -> None:
    info = inspect_pdf(render_pdf(invoice, supplier))
    assert info.pages == 1
    assert info.fonts and all(f.replace("-", "").startswith("JetBrainsMono") for f in info.fonts), (
        f"fonts: {info.fonts}"
    )
    assert info.images == 0
    width, height = info.size
    assert abs(width - 595.28) < 1 and abs(height - 841.89) < 1, f"MediaBox {width}×{height}"


def test_a_25_line_invoice_paginates_beyond_the_first_page(invoice: Invoice, supplier: Supplier) -> None:
    items = [LineItem(description=f"Task {i + 1}", detail="Detail", quantity=1, rate=100) for i in range(25)]
    info = inspect_pdf(render_pdf(invoice.model_copy(update={"line_items": items}), supplier))
    assert info.pages > 1, f"pages: {info.pages}"


def test_stored_invoice_json_is_validated(invoice: Invoice) -> None:
    data = invoice.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert validate_invoice(json.dumps(data)) == invoice
    with pytest.raises(ValidationError) as exc:
        validate_invoice(json.dumps({**data, "number": "MS-42", "lineItems": [], "extra": 1}))
    assert any(e.startswith("/number ") for e in exc.value.errors)
    assert any(e.startswith("/lineItems ") for e in exc.value.errors)
    assert any(e.startswith("/extra ") for e in exc.value.errors)


# --- HTTP ---


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_get_form(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert '<form id="invoice" method="post" action="/invoice">' in res.text
    assert 'value="1"' in res.text  # invoiceNumberStart from the saved defaults
    assert "Next in sequence: MS-0001" in res.text
    assert 'value="IT &amp; Software Consultancy Services"' in res.text
    assert '<option value="days" selected>Days</option>' in res.text


def test_post_invalid_invoice_returns_422_json(client: TestClient) -> None:
    body = {**FORM_BODY, "clientId": "", "description": [""], "detail": [""], "quantity": [""]}
    res = client.post("/invoice", data=body)
    assert res.status_code == 422
    assert res.json() == {"errors": ["Add at least one line item", "Choose a client"]}


def test_post_valid_invoice_returns_pdf_and_advances_counter(client: TestClient) -> None:
    stored = create_client(EXAMPLE_CLIENT)
    res = client.post("/invoice", data={**FORM_BODY, "clientId": stored.id})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"] == 'inline; filename="MS-0042.pdf"'
    assert res.content.startswith(b"%PDF")
    assert "Next in sequence: MS-0043" in client.get("/").text


def test_unexpected_errors_are_json_500s(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr("volition.main.list_clients", broken)
    res = client.get("/")
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
def test_cross_origin_posts_are_rejected(client: TestClient, supplier: Supplier, headers: dict[str, str]) -> None:
    res = client.post("/supplier", data={"sortCode": "12-34-56"}, headers=headers, follow_redirects=False)
    assert res.status_code == 403
    assert res.json() == {"errors": ["Cross-origin request rejected"]}
    assert load_supplier() == supplier


@pytest.mark.parametrize(
    "headers",
    [{}, {"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}, {"Origin": "http://localhost"}],
)
def test_same_origin_and_non_browser_posts_are_allowed(client: TestClient, headers: dict[str, str]) -> None:
    res = client.post("/clients/missing/delete", headers=headers, follow_redirects=False)
    assert res.status_code == 404


def test_cross_origin_gets_are_allowed(client: TestClient) -> None:
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1:3000", "[::1]:3000"])
def test_local_hosts_are_allowed(client: TestClient, host: str) -> None:
    assert client.get("/health", headers={"Host": host}).status_code == 200


def test_other_hosts_are_rejected(client: TestClient, supplier: Supplier) -> None:
    """A DNS-rebound page is same-origin to the browser, so only the Host header gives it away."""
    headers = {"Host": "evil.example:3000", "Sec-Fetch-Site": "same-origin", "Origin": "http://evil.example:3000"}
    assert client.get("/", headers=headers).status_code == 400
    res = client.post("/supplier", data={"sortCode": "12-34-56"}, headers=headers)
    assert res.status_code == 400
    assert load_supplier() == supplier


@pytest.mark.parametrize(
    ("env", "hosts"),
    [
        (None, ["127.0.0.1", "localhost", "[::1]"]),
        ("", ["127.0.0.1", "localhost", "[::1]"]),
        (" Invoices.example.com , localhost,", ["invoices.example.com", "localhost"]),
        ("*", ["*"]),
    ],
)
def test_allowed_hosts_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, env: str | None, hosts: list[str]
) -> None:
    if env is None:
        monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_HOSTS", env)
    assert allowed_hosts() == hosts


def test_assets_are_served(client: TestClient) -> None:
    res = client.get("/assets/ms-mark.svg")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/svg+xml")
