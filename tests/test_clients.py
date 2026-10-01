import json
import re
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import FormData

from volition.errors import ValidationError
from volition.models import ClientDetails, PresetLineItem
from volition.store import db
from volition.store.clients import create_client, delete_client, get_client, list_clients, update_client
from volition.store.invoice_numbers import next_invoice_number
from volition.web.pages.invoice import parse_invoice_form

ACME = ClientDetails(
    name="Acme Ltd",
    contact="Accounts",
    address=["1 Road", "Town"],
    email="ap@acme.co.uk",
    vat=False,
    unit="hours",
    line_items=[PresetLineItem(description="Support", rate=90), PresetLineItem(description="Travel")],
    notes="PO 123",
)


# --- Store ---


def test_a_created_client_round_trips_with_a_uuid7_id() -> None:
    created = create_client(ACME)
    assert uuid.UUID(created.id).version == 7
    assert get_client(created.id) == created
    assert created.model_dump(exclude={"id"}) == ACME.model_dump()


def test_clients_list_alphabetically_ignoring_case() -> None:
    for name in ["zeta", "Beta", "alpha"]:
        create_client(ClientDetails(name=name, address=["x"]))
    assert [c.name for c in list_clients()] == ["alpha", "Beta", "zeta"]


def test_names_are_unique_ignoring_case() -> None:
    create_client(ACME)
    with pytest.raises(ValidationError) as exc:
        create_client(ClientDetails(name="ACME LTD", address=["x"]))
    assert exc.value.errors == ["A client named ACME LTD already exists"]


def test_renaming_onto_another_clients_name_is_rejected() -> None:
    create_client(ACME)
    other = create_client(ClientDetails(name="Other", address=["x"]))
    with pytest.raises(ValidationError):
        update_client(other.id, ClientDetails(name="acme ltd", address=["x"]))
    assert get_client(other.id) == other


def test_updating_replaces_details_and_line_items() -> None:
    created = create_client(ACME)
    changed = ClientDetails(name="Acme Group", address=["2 Road"], line_items=[PresetLineItem(description="Build")])
    updated = update_client(created.id, changed)
    assert updated is not None and get_client(created.id) == updated
    assert updated.vat is None and [i.description for i in updated.line_items] == ["Build"]


def test_updating_or_deleting_a_missing_client_says_so() -> None:
    assert update_client("nope", ACME) is None
    assert delete_client("nope") is False
    assert get_client("nope") is None


def test_deleting_a_client_cascades_to_its_line_items() -> None:
    created = create_client(ACME)
    assert delete_client(created.id) is True
    assert get_client(created.id) is None
    with db.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM client_line_items").fetchone()[0] == 0


def test_a_failed_transaction_rolls_back() -> None:
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("INSERT INTO clients (id, name, address) VALUES ('x', 'Rolled back', 'a')")
        raise RuntimeError
    assert list_clients() == []


def test_migrations_apply_once_and_record_the_schema_version() -> None:
    db.migrate()
    db.migrate()
    conn = sqlite3.connect(db.db_path())
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    conn.close()


# --- Client form ---


CLIENT_FORM: dict[str, str | list[str]] = {
    "name": "Acme Ltd",
    "contact": "Accounts",
    "email": "ap@acme.co.uk",
    "address": "1 Road\r\n\r\nTown\r\n",
    "unit": "hours",
    "vat": "no",
    "description": ["Support", "", "Travel"],
    "detail": ["", "", ""],
    "rate": ["90", "", ""],
    "notes": "PO 123",
}


def test_creating_a_client_from_the_form_redirects_to_the_list(client: TestClient) -> None:
    res = client.post("/clients", data=CLIENT_FORM, follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/clients"
    [stored] = list_clients()
    assert stored.model_dump(exclude={"id"}) == ACME.model_dump()
    page = client.get("/clients").text
    assert f'<a href="/clients/{stored.id}">Acme Ltd</a>' in page


def test_blank_choices_fall_back_to_defaults(client: TestClient) -> None:
    body = {"name": "Plain", "address": "x", "unit": "", "vat": "", "description": [""], "detail": [""], "rate": [""]}
    assert client.post("/clients", data=body, follow_redirects=False).status_code == 303
    [stored] = list_clients()
    assert (stored.unit, stored.vat, stored.line_items, stored.notes) == (None, None, [], None)


def test_an_invalid_client_form_is_re_rendered_with_its_errors_and_values(client: TestClient) -> None:
    body = {
        **CLIENT_FORM,
        "name": "",
        "address": "",
        "email": "nope",
        "rate": ["-1", "", "abc"],
        "detail": ["", "x", ""],
    }
    body["description"] = ["Support", "", "Travel"]
    res = client.post("/clients", data=body)
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("text/html")
    errors = re.findall(r"<li>(.*?)</li>", res.text)
    assert errors == [
        "Name is required",
        "Address is required",
        "Line 1: rate must be a whole number of 0 or more",
        "Line 2: description is required",
        "Line 3: rate must be a whole number of 0 or more",
    ]
    assert 'value="ap@acme.co.uk"' not in res.text and 'value="nope"' in res.text
    assert list_clients() == []


def test_schema_errors_on_the_client_form_are_reported(client: TestClient) -> None:
    res = client.post("/clients", data={**CLIENT_FORM, "email": "nope"})
    assert res.status_code == 422
    assert re.findall(r"<li>(/\w+) ", res.text) == ["/email"]


def test_a_duplicate_name_is_reported_on_the_form(client: TestClient) -> None:
    create_client(ACME)
    res = client.post("/clients", data={**CLIENT_FORM, "name": "acme ltd"})
    assert res.status_code == 422
    assert "A client named acme ltd already exists" in res.text


def test_editing_a_client(client: TestClient) -> None:
    stored = create_client(ACME)
    page = client.get(f"/clients/{stored.id}").text
    assert 'value="Acme Ltd"' in page and "1 Road\nTown</textarea>" in page
    assert '<option value="no" selected>No VAT</option>' in page
    assert f'action="/clients/{stored.id}/delete"' in page

    res = client.post(f"/clients/{stored.id}", data={**CLIENT_FORM, "name": "Acme Group"}, follow_redirects=False)
    assert res.status_code == 303
    assert get_client(stored.id).name == "Acme Group"  # type: ignore[union-attr]


def test_deleting_a_client(client: TestClient) -> None:
    stored = create_client(ACME)
    res = client.post(f"/clients/{stored.id}/delete", follow_redirects=False)
    assert res.status_code == 303
    assert list_clients() == []


def test_missing_clients_are_404s(client: TestClient) -> None:
    assert client.get("/clients/nope").status_code == 404
    assert client.post("/clients/nope", data=CLIENT_FORM).status_code == 404
    assert client.post("/clients/nope/delete").status_code == 404


def test_new_client_form(client: TestClient) -> None:
    res = client.get("/clients/new")
    assert res.status_code == 200
    assert '<form id="client" method="post" action="/clients">' in res.text
    assert "Delete" not in res.text


# --- Invoice form dropdown ---


def client_data(html: str) -> list[dict]:
    match = re.search(r'<script type="application/json" id="client-data">(.*?)</script>', html, re.DOTALL)
    assert match
    return json.loads(match.group(1))


def test_without_clients_the_invoice_form_asks_for_one(client: TestClient) -> None:
    page = client.get("/").text
    assert '<a href="/clients/new">Add one</a>' in page
    assert '<button type="submit" class="primary" disabled>' in page
    assert 'name="clientId"' not in page


def test_a_lone_client_is_preselected_with_its_defaults(client: TestClient) -> None:
    stored = create_client(ACME)
    page = client.get("/").text
    assert f'<option value="{stored.id}" selected>Acme Ltd</option>' in page
    assert "Choose a client…" not in page
    assert "<li>Accounts</li>" in page and "<li>ap@acme.co.uk</li>" in page
    assert 'value="Support"' in page and 'value="90"' in page
    assert '<option value="hours" selected>Hours</option>' in page
    assert ">PO 123</textarea>" in page


def test_with_several_clients_one_must_be_chosen(client: TestClient) -> None:
    create_client(ACME)
    plain = create_client(ClientDetails(name="Plain", address=["x"]))
    page = client.get("/").text
    assert '<option value="" disabled selected>Choose a client…</option>' in page
    assert " selected>Acme Ltd<" not in page
    by_id = {c["id"]: c for c in client_data(page)}
    # A client without its own invoice defaults gets the global ones.
    assert by_id[plain.id] == {
        "id": plain.id,
        "name": "Plain",
        "billTo": ["x"],
        "vat": True,
        "unit": "days",
        "lineItems": [{"description": "IT & Software Consultancy Services", "rate": 650}],
        "notes": "",
    }


def test_client_data_cannot_break_out_of_its_script_tag(client: TestClient) -> None:
    create_client(ClientDetails(name="</script><script>alert(1)</script>", address=["x"]))
    page = client.get("/").text
    assert "<script>alert(1)" not in page
    assert client_data(page)[0]["name"] == "</script><script>alert(1)</script>"


def test_the_invoice_bills_the_stored_client(client: TestClient) -> None:
    stored = create_client(ACME)
    body: dict[str, str | list[str]] = {
        "number": "7",
        "issueDate": "2026-09-19",
        "clientId": stored.id,
        "unit": "hours",
        "description": ["Support"],
        "detail": [""],
        "quantity": ["3"],
        "rate": ["90"],
        # Tampered bill-to fields are ignored: only the stored client is billed.
        "clientName": "Someone Else",
    }
    invoice = parse_invoice_form(
        FormData([(k, v) for k, vs in body.items() for v in (vs if isinstance(vs, list) else [vs])]), get_client
    )
    assert invoice.client.model_dump(by_alias=True, exclude_none=True) == {
        "name": "Acme Ltd",
        "contact": "Accounts",
        "address": ["1 Road", "Town"],
        "email": "ap@acme.co.uk",
    }
    res = client.post("/invoice", data=body)
    assert res.status_code == 200, res.text
    assert next_invoice_number(1) == 8
