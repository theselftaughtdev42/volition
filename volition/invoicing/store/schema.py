"""Invoicing's schema: one script per version. Append new steps, never edit applied ones.

Every table is prefixed with the module's slug. The supplier, the defaults and the counter are single-row tables
(`id` is always 1) holding nothing until the first run saves them.
"""

MIGRATIONS = (
    """
    CREATE TABLE invoicing_clients (
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

    CREATE TABLE invoicing_client_line_items (
        id INTEGER PRIMARY KEY,
        client_id TEXT NOT NULL REFERENCES invoicing_clients (id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        description TEXT NOT NULL,
        detail TEXT,
        rate INTEGER CHECK (rate >= 0),
        UNIQUE (client_id, position)
    ) STRICT;

    -- The Supplier model as JSON.
    CREATE TABLE invoicing_supplier (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        data TEXT NOT NULL
    ) STRICT;

    -- The Defaults model as JSON.
    CREATE TABLE invoicing_defaults (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        data TEXT NOT NULL
    ) STRICT;

    -- The highest invoice number generated so far.
    CREATE TABLE invoicing_counter (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_invoice_number INTEGER NOT NULL
    ) STRICT;
    """,
)
