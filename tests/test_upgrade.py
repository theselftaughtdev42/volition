"""Upgrading a database from before modules (v0.1.x) at startup, as the production app does."""

import re
import sqlite3
from collections.abc import Iterator, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from volition import invoicing
from volition.core.app import create_app
from volition.core.store import db
from volition.upgrade import PRE_MODULE_UPGRADE

#: The v0.1.x schema, exactly as its only migration created it.
V1_SCHEMA = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value ANY NOT NULL
) STRICT;

CREATE TABLE clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    contact TEXT,
    email TEXT,
    -- One line per row, newline-joined.
    address TEXT NOT NULL,
    vat INTEGER CHECK (vat IN (0, 1)),
    unit TEXT CHECK (unit IN ('days', 'hours', 'items')),
    notes TEXT
) STRICT;

CREATE TABLE client_line_items (
    id INTEGER PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    description TEXT NOT NULL,
    detail TEXT,
    rate INTEGER CHECK (rate >= 0),
    UNIQUE (client_id, position)
) STRICT;

PRAGMA user_version = 1;
"""

#: As v0.1.x stored them: JSON text, keys camelCase.
SUPPLIER = (
    '{"name":"Mackay Software","legalName":"Mackay Software Limited",'
    '"address":["Mansion House, Manchester Rd","Altrincham, Cheshire","WA14 4RW"],'
    '"website":"www.mackaysoftware.com","email":"tim@mackaysoftware.com","companyNumber":"15289765",'
    '"registeredIn":"England & Wales","vatNumber":"GB 459 3303 82","paymentTermsDays":21,'
    '"bank":{"bankName":"Monzo","accountName":"Mackay Software Limited",'
    '"sortCode":"12-34-56","accountNumber":"87654321"}}'
)
DEFAULTS = (
    '{"invoiceNumberStart":7,"vat":true,"unit":"hours",'
    '"lineItems":[{"description":"Retained support","detail":null,"rate":95}],"notes":"Thanks for your business"}'
)
DATA = """
INSERT INTO clients (id, name, contact, email, address, vat, unit, notes) VALUES
    ('c-acme', 'Acme Ltd', 'Accounts', 'ap@acme.co.uk', '1 Road' || char(10) || 'Town', 0, 'days', 'PO 123'),
    ('c-plain', 'Plain Co', NULL, NULL, 'Somewhere', NULL, NULL, NULL);
INSERT INTO client_line_items (client_id, position, description, detail, rate) VALUES
    ('c-acme', 0, 'Backend development', 'Sprints', 550),
    ('c-acme', 1, 'Travel', NULL, NULL);
"""


def seed(meta: Mapping[str, str | int], data: str = "") -> Path:
    """A v0.1.x database in DATA_DIR."""
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA + data)
    conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta.items())
    conn.commit()
    conn.close()
    return path


def started() -> TestClient:
    return TestClient(create_app([invoicing.module], PRE_MODULE_UPGRADE), base_url="http://localhost")


@pytest.fixture
def upgraded() -> Iterator[TestClient]:
    seed({"supplier": SUPPLIER, "defaults": DEFAULTS, "lastInvoiceNumber": 41}, DATA)
    with started() as c:
        yield c


def test_the_suppliers_identity_becomes_the_business(upgraded: TestClient) -> None:
    page = upgraded.get("/business").text
    assert "Welcome." not in page
    for value in [
        "Mackay Software",
        "Mackay Software Limited",
        "tim@mackaysoftware.com",
        "www.mackaysoftware.com",
        "15289765",
        "England &amp; Wales",
        "GB 459 3303 82",
    ]:
        assert f'value="{value}"' in page
    assert "Mansion House, Manchester Rd\nAltrincham, Cheshire\nWA14 4RW</textarea>" in page
    assert '<span class="label">Mackay Software Limited</span>' in page


def test_the_defaults_payment_terms_and_bank_details_become_the_invoicing_settings(upgraded: TestClient) -> None:
    page = upgraded.get("/invoicing/settings").text
    assert "Before the first invoice" not in page
    for value in ["7", "Retained support", "95", "21", "Monzo", "Mackay Software Limited", "12-34-56", "87654321"]:
        assert f'value="{value}"' in page
    assert "Thanks for your business" in page
    assert '<option value="hours" selected>' in page
    assert 'name="vat" type="checkbox" checked' in page


def test_the_clients_and_their_line_items_carry_over(upgraded: TestClient) -> None:
    page = upgraded.get("/invoicing/clients").text
    assert re.findall(r'<a href="/invoicing/clients/([^"]+)">([^<]+)</a>', page) == [
        ("c-acme", "Acme Ltd"),
        ("c-plain", "Plain Co"),
    ]
    page = upgraded.get("/invoicing/clients/c-acme").text
    for value in ["Accounts", "ap@acme.co.uk", "Backend development", "Sprints", "550", "Travel"]:
        assert f'value="{value}"' in page
    assert "PO 123" in page


def test_invoice_numbering_continues_from_the_last_one_issued(upgraded: TestClient) -> None:
    assert "Next in sequence: MS-0042" in upgraded.get("/invoicing/").text


def test_invoices_print_the_old_supplier_and_bank_details(upgraded: TestClient) -> None:
    body = {
        "number": "42",
        "issueDate": "2026-10-01",
        "unit": "days",
        "clientId": "c-acme",
        "description": "Backend development",
        "quantity": "3",
        "rate": "550",
    }
    res = upgraded.post("/invoicing/invoice", data=body)
    assert res.status_code == 200, res.text
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(res.content)).pages)
    for value in [
        "Mackay Software Limited",
        "Mansion House, Manchester Rd",
        "Registered in England & Wales no. 15289765",
        "Acme Ltd",
        "Bank transfer within 21 days.",
        "22 Oct 2026",  # due: issue date + the old payment terms
        "Monzo",
        "12-34-56",
        "87654321",
    ]:
        assert value in text, value
    assert "Next in sequence: MS-0043" in upgraded.get("/invoicing/").text


@pytest.mark.parametrize(
    ("meta", "first_page"),
    [
        ({}, "/business"),
        # The settings need the defaults as well as the supplier's bank details.
        ({"supplier": SUPPLIER}, "/invoicing/settings"),
        ({"defaults": DEFAULTS}, "/business"),
    ],
)
def test_an_upgraded_database_whose_setup_was_never_completed_lands_in_the_first_run(
    meta: dict[str, str], first_page: str
) -> None:
    seed(meta)
    with started() as c:
        res = c.get("/invoicing/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == first_page


def test_a_failing_upgrade_leaves_the_database_unchanged_and_fails_startup() -> None:
    path = seed({"supplier": SUPPLIER, "defaults": DEFAULTS, "lastInvoiceNumber": "forty-one"}, DATA)
    before = path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError), started():
        pass
    assert path.read_bytes() == before


def schema() -> tuple[list[tuple[Any, ...]], dict[str, int], int]:
    """Every table and index as created, the recorded module versions and user_version."""
    conn = sqlite3.connect(db.db_path())
    try:
        objects = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY name").fetchall()
        versions = dict(conn.execute("SELECT module, version FROM schema_versions"))
        return objects, versions, conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_a_fresh_database_and_an_upgraded_one_have_the_same_schema(
    isolated_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with started():
        pass
    fresh = schema()
    monkeypatch.setenv("DATA_DIR", str(isolated_dirs / "upgraded"))
    seed({"supplier": SUPPLIER, "defaults": DEFAULTS, "lastInvoiceNumber": 41}, DATA)
    with started():
        pass
    assert schema() == fresh
    objects, versions, _ = fresh
    assert [name for type_, name, *_ in objects if type_ == "table"] == [
        "business",
        "invoicing_client_line_items",
        "invoicing_clients",
        "invoicing_counter",
        "invoicing_settings",
        "schema_versions",
    ]
    assert versions == {"core": 1, "invoicing": 1}
