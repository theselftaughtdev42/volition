"""The one-off upgrade of a database from before modules (v0.1.x), which spans the modules so lives in the root.

Back then invoicing's tables were unprefixed and its supplier, defaults and invoice counter were rows of a shared
`meta` key/value table. Core and invoicing's first migrations create the new tables; this moves the data across.
"""

from volition.core.store.db import Bootstrap

PRE_MODULE_UPGRADE = Bootstrap(
    versions={"core": 1, "invoicing": 1},
    script="""
    INSERT INTO invoicing_clients (id, name, contact, email, address, vat, unit, notes)
    SELECT id, name, contact, email, address, vat, unit, notes FROM clients;

    INSERT INTO invoicing_client_line_items (id, client_id, position, description, detail, rate)
    SELECT id, client_id, position, description, detail, rate FROM client_line_items;

    INSERT INTO invoicing_supplier (id, data) SELECT 1, value FROM meta WHERE key = 'supplier';
    INSERT INTO invoicing_defaults (id, data) SELECT 1, value FROM meta WHERE key = 'defaults';
    INSERT INTO invoicing_counter (id, last_invoice_number) SELECT 1, value FROM meta WHERE key = 'lastInvoiceNumber';

    DROP TABLE client_line_items;
    DROP TABLE clients;
    DROP TABLE meta;
    """,
)
