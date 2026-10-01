"""Invoicing's schema: one script per version. Append new steps, never edit applied ones."""

MIGRATIONS = (
    """
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
    """,
)
