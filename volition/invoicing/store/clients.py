"""Clients the invoice form bills, with their own invoice defaults."""

import sqlite3
import uuid

from volition.core.errors import ValidationError
from volition.core.store.db import transaction
from volition.invoicing.models import ClientDetails, ClientRecord, PresetLineItem


def _record(conn: sqlite3.Connection, row: sqlite3.Row) -> ClientRecord:
    items = conn.execute(
        "SELECT description, detail, rate FROM invoicing_client_line_items WHERE client_id = ? ORDER BY position",
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
        line_items=[PresetLineItem(description=i["description"], detail=i["detail"], rate=i["rate"]) for i in items],
        notes=row["notes"],
    )


def list_clients() -> list[ClientRecord]:
    """Alphabetical by name."""
    with transaction() as conn:
        rows = conn.execute("SELECT * FROM invoicing_clients ORDER BY name, id").fetchall()
        return [_record(conn, row) for row in rows]


def get_client(client_id: str) -> ClientRecord | None:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM invoicing_clients WHERE id = ?", (client_id,)).fetchone()
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
                "INSERT INTO invoicing_clients (id, name, contact, email, address, vat, unit, notes)"
                " VALUES (:id, :name, :contact, :email, :address, :vat, :unit, :notes)",
                values,
            )
        else:
            cursor = conn.execute(
                "UPDATE invoicing_clients SET name = :name, contact = :contact, email = :email, address = :address,"
                " vat = :vat, unit = :unit, notes = :notes WHERE id = :id",
                values,
            )
            if cursor.rowcount == 0:
                return False
    except sqlite3.IntegrityError as e:
        if "invoicing_clients.name" in str(e):
            raise ValidationError("client", [f"A client named {details.name} already exists"]) from None
        raise
    conn.execute("DELETE FROM invoicing_client_line_items WHERE client_id = ?", (client_id,))
    conn.executemany(
        "INSERT INTO invoicing_client_line_items (client_id, position, description, detail, rate) VALUES (?, ?, ?, ?, ?)",
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
        return conn.execute("DELETE FROM invoicing_clients WHERE id = ?", (client_id,)).rowcount > 0
