"""The subscriptions table: its schema (one script per version: append new steps, never edit applied ones) and CRUD."""

import sqlite3
import uuid

from volition.core.store.db import transaction
from volition.subscriptions.models import SubscriptionDetails, SubscriptionRecord

MIGRATIONS = (
    """
    CREATE TABLE subscriptions_items (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        vendor TEXT,
        cycle TEXT NOT NULL CHECK (cycle IN ('monthly', 'yearly')),
        -- ISO date.
        renews_on TEXT NOT NULL,
        currency TEXT NOT NULL CHECK (currency IN ('GBP', 'USD', 'EUR')),
        -- Pence (or cents) per cycle, in currency; cost_gbp only for another currency.
        cost INTEGER NOT NULL CHECK (cost >= 0),
        cost_gbp INTEGER CHECK (cost_gbp >= 0),
        auto_renews INTEGER NOT NULL CHECK (auto_renews IN (0, 1)),
        paid_with TEXT
    ) STRICT;
    """,
)

_COLUMNS = ("name", "vendor", "cycle", "renews_on", "currency", "cost", "cost_gbp", "auto_renews", "paid_with")


def _record(row: sqlite3.Row) -> SubscriptionRecord:
    return SubscriptionRecord.model_validate({**dict(row), "auto_renews": bool(row["auto_renews"])}, strict=False)


def _values(subscription_id: str, details: SubscriptionDetails) -> dict[str, object]:
    return {
        "id": subscription_id,
        **details.model_dump(include=set(_COLUMNS), mode="json"),
        "auto_renews": int(details.auto_renews),
    }


def list_subscriptions() -> list[SubscriptionRecord]:
    """Alphabetical by name."""
    with transaction() as conn:
        rows = conn.execute("SELECT * FROM subscriptions_items ORDER BY name COLLATE NOCASE, id").fetchall()
    return [_record(row) for row in rows]


def get_subscription(subscription_id: str) -> SubscriptionRecord | None:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM subscriptions_items WHERE id = ?", (subscription_id,)).fetchone()
    return None if row is None else _record(row)


def create_subscription(details: SubscriptionDetails) -> SubscriptionRecord:
    subscription_id = str(uuid.uuid7())
    with transaction() as conn:
        conn.execute(
            "INSERT INTO subscriptions_items"
            " (id, name, vendor, cycle, renews_on, currency, cost, cost_gbp, auto_renews, paid_with) VALUES"
            " (:id, :name, :vendor, :cycle, :renews_on, :currency, :cost, :cost_gbp, :auto_renews, :paid_with)",
            _values(subscription_id, details),
        )
    return SubscriptionRecord(id=subscription_id, **dict(details))


def update_subscription(subscription_id: str, details: SubscriptionDetails) -> SubscriptionRecord | None:
    """None if there is no such subscription."""
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE subscriptions_items SET name = :name, vendor = :vendor, cycle = :cycle, renews_on = :renews_on,"
            " currency = :currency, cost = :cost, cost_gbp = :cost_gbp, auto_renews = :auto_renews,"
            " paid_with = :paid_with WHERE id = :id",
            _values(subscription_id, details),
        )
    return None if cursor.rowcount == 0 else SubscriptionRecord(id=subscription_id, **dict(details))


def delete_subscription(subscription_id: str) -> bool:
    """False if there was no such subscription."""
    with transaction() as conn:
        return conn.execute("DELETE FROM subscriptions_items WHERE id = ?", (subscription_id,)).rowcount > 0
