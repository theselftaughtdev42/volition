"""Clients the invoice form bills, stored in the database with their own invoice defaults."""

import sqlite3
import uuid
from typing import Annotated

from pydantic import EmailStr, Field

from volition.config import ValidationError
from volition.db import transaction
from volition.invoice import Client, Model, Unit


class ClientLineItem(Model):
    """A line an invoice for this client starts with. Quantities vary per invoice, so there is none here."""

    description: Annotated[str, Field(min_length=1)]
    detail: str | None = None
    rate: Annotated[int, Field(ge=0)] | None = None


class ClientDetails(Model):
    """Everything about a client that the client form edits."""

    name: Annotated[str, Field(min_length=1)]
    contact: str | None = None
    address: Annotated[list[str], Field(min_length=1)]
    email: EmailStr | None = None
    #: Invoice defaults for this client; None falls back to defaults.json.
    vat: bool | None = None
    unit: Unit | None = None
    line_items: list[ClientLineItem] = []
    notes: str | None = None

    def bill_to(self) -> Client:
        return Client(name=self.name, contact=self.contact, address=self.address, email=self.email)


class ClientRecord(ClientDetails):
    #: A UUIDv7, as text.
    id: str


def _record(conn: sqlite3.Connection, row: sqlite3.Row) -> ClientRecord:
    items = conn.execute(
        "SELECT description, detail, rate FROM client_line_items WHERE client_id = ? ORDER BY position",
        (row["id"],),
    ).fetchall()
    return ClientRecord(
        id=row["id"],
        name=row["name"],
        contact=row["contact"],
        address=row["address"].split("\n"),
        email=row["email"],
        vat=None if row["vat"] is None else bool(row["vat"]),
        unit=row["unit"],
        line_items=[ClientLineItem(description=i["description"], detail=i["detail"], rate=i["rate"]) for i in items],
        notes=row["notes"],
    )


def list_clients() -> list[ClientRecord]:
    """Alphabetical by name."""
    with transaction() as conn:
        rows = conn.execute("SELECT * FROM clients ORDER BY name, id").fetchall()
        return [_record(conn, row) for row in rows]


def get_client(client_id: str) -> ClientRecord | None:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        return None if row is None else _record(conn, row)


def _write(conn: sqlite3.Connection, client_id: str, details: ClientDetails, *, insert: bool) -> bool:
    """Inserts or updates the client row and replaces its line items. False if there was no row to update."""
    values = {
        "id": client_id,
        "name": details.name,
        "contact": details.contact,
        "email": details.email,
        "address": "\n".join(details.address),
        "vat": None if details.vat is None else int(details.vat),
        "unit": details.unit,
        "notes": details.notes,
    }
    try:
        if insert:
            conn.execute(
                "INSERT INTO clients (id, name, contact, email, address, vat, unit, notes)"
                " VALUES (:id, :name, :contact, :email, :address, :vat, :unit, :notes)",
                values,
            )
        else:
            cursor = conn.execute(
                "UPDATE clients SET name = :name, contact = :contact, email = :email, address = :address,"
                " vat = :vat, unit = :unit, notes = :notes WHERE id = :id",
                values,
            )
            if cursor.rowcount == 0:
                return False
    except sqlite3.IntegrityError as e:
        if "clients.name" in str(e):
            raise ValidationError("client", [f"A client named {details.name} already exists"]) from None
        raise
    conn.execute("DELETE FROM client_line_items WHERE client_id = ?", (client_id,))
    conn.executemany(
        "INSERT INTO client_line_items (client_id, position, description, detail, rate) VALUES (?, ?, ?, ?, ?)",
        [(client_id, i, item.description, item.detail, item.rate) for i, item in enumerate(details.line_items)],
    )
    return True


def create_client(details: ClientDetails) -> ClientRecord:
    """Raises ValidationError if another client already has the name (ignoring case)."""
    client_id = str(uuid.uuid7())
    with transaction() as conn:
        _write(conn, client_id, details, insert=True)
    return ClientRecord(id=client_id, **dict(details))


def update_client(client_id: str, details: ClientDetails) -> ClientRecord | None:
    """None if there is no such client. Raises ValidationError on a duplicate name."""
    with transaction() as conn:
        if not _write(conn, client_id, details, insert=False):
            return None
    return ClientRecord(id=client_id, **dict(details))


def delete_client(client_id: str) -> bool:
    """Deletes the client and (by cascade) its line items. False if there was no such client."""
    with transaction() as conn:
        return conn.execute("DELETE FROM clients WHERE id = ?", (client_id,)).rowcount > 0
