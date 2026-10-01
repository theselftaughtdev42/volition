# volition

Back office for Mackay Software: one small web app made of a shell plus modules. Invoicing is the first module; it produces branded A4 PDF invoices for clients chosen from a list.

## Setup

Requires Python 3.14, [uv](https://docs.astral.sh/uv/) and Pango, which [WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) renders PDFs with (`brew install pango`, or `apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`).

```sh
make install
make start      # http://127.0.0.1:3000, honours HOST and PORT
```

Also: `make dev`, `make test`, `make lint`, `make format`.

## Docker

The image listens on port 3000 and keeps its database (the business, each module's data and settings) in `/data`. Mount it: the database holds bank details and is never baked into the image.

```sh
make docker.build && make docker.run    # mounts ./data
```

Pushing a `v*` tag publishes `ghcr.io/theselftaughtdev42/volition` (see `.github/workflows/publish.yml`). `GET /health` backs the container healthcheck.

To cut a release, run `make release BUMP=patch` (or `minor`/`major`, or `V=1.2.3`) from a clean `main` that matches `origin/main`. It runs lint and tests, bumps the version in `pyproject.toml` and `uv.lock`, commits, tags `vX.Y.Z` and asks before pushing.

## Using it

Volition opens on a home page with a card per module. Every page has the top nav (each module, then Business), plus the current module's own pages.

On the first run every page redirects to ask for what's missing:

1. `/business`: who the business is. The trading and legal names, address, email, website, company number and where it is registered, and VAT number. Every module can use them; invoices print them.
2. `/invoicing/settings`, when you first open Invoicing: the invoice defaults (first invoice number, whether VAT is ticked, unit, line items with description, detail and rate, and notes), payment terms and bank details.

Both can be changed on those pages later.

There is no login, so anyone who can reach the port can use the app. Form posts from other websites are rejected (by `Sec-Fetch-Site`, else `Origin`), so a page you visit can't change the bank details behind your back, and requests for hostnames outside `ALLOWED_HOSTS` are refused.

## Invoicing

The invoice form is at `/invoicing/`, clients at `/invoicing/clients` and settings at `/invoicing/settings`.

### Numbering and dates

Invoice numbers are `MS-` plus a zero-padded integer. The form suggests the next one: the first invoice number from the settings, then the last generated number + 1. The number can be overridden; regenerating an older invoice never winds the counter back. Raising the first invoice number above the counter jumps ahead.

The period defaults to the current calendar month, the issue date to today (in `TIMEZONE`), and the due date (if left blank) to issue date + the payment terms.

### Clients

Each client has bill-to details (name, contact, address, email) and optional invoice defaults: VAT, unit, line items (description, detail and rate; quantities are entered per invoice) and notes. Anything a client leaves unset falls back to the invoicing settings.

The invoice form bills whichever client is chosen from its dropdown, exactly as stored: fix a client's details on its page rather than on the invoice. Choosing a client replaces the VAT, unit, line items and notes with that client's defaults. A lone client is preselected; with several, one must be chosen. Names are unique, ignoring case, and client ids are UUIDv7s.

### Invoice rules

- Everything is in GBP. Quantities and rates are whole numbers (rates in whole pounds); money is integer pence internally.
- `lineTotal = quantity × rate`; `vat = subtotal × 20%` (`VAT_PERCENT` in `volition/invoicing/invoices.py`) when the VAT box is ticked; `total = subtotal + vat`.
- Unticked VAT hides the VAT row and the VAT number.
- Dates print as `19 Sep 2026`, the period as `1 Sep – 30 Sep 2026`, money as `£4,250.00`.
- Long invoices continue onto further pages with the table header repeated; the totals block never splits.

## Environment

| Variable | Default | |
| --- | --- | --- |
| `PORT` | `3000` | Used by `python -m volition` (and `fastapi dev`/`run`, whose own default is 8000). |
| `HOST` | `127.0.0.1` | Used by `python -m volition`. Set `0.0.0.0` to listen beyond localhost. |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,[::1]` | Comma-separated hostnames the app answers to; other `Host` headers get a 400 (guarding against DNS rebinding). Add yours when serving under a domain name or LAN address, or `*` to allow any. Read at startup. |
| `TIMEZONE` | `Europe/London` | The business's time zone, as an IANA name (e.g. `UTC`, `Europe/Dublin`). It decides what "today" is, for the invoice form's default dates. An unknown name stops the app starting. |
| `DATA_DIR` | `./data` | Holds `volition.db` (SQLite: the business, plus each module's data and settings). Persist it across deploys. |

## Adding a module

Volition is a modular monolith: one process, one image and one SQLite file. `volition/core` is the shell (home page, nav, Business, shared styling, database plumbing, migrations, security middleware); each module is a sibling package such as `volition/invoicing`.

### The contract

A module exposes a `Module` (`volition/core/modules.py`):

- `slug`: e.g. `invoicing`. Its URL prefix, template namespace, migration namespace and table prefix. Never `core`.
- `title` and `description`: shown on the home page card and in the top nav.
- `router`: a FastAPI `APIRouter`, mounted at `/<slug>`. Every route already requires the Business to be saved.
- `nav`: the module's own pages as `NavLink(title, path)`, in order, with paths relative to the prefix (`"/"` is the module's home).
- `migrations`: its schema, one SQL script per version.
- `templates`: its template directory. Build the module's Jinja environment with `volition.core.templates.environment({slug: directory})` so its pages can extend the shell's `base.html` and are loaded as `<slug>/page.html`.

A module owns its first-run setup: a dependency that raises `SetupIncomplete(path)` (`volition/core/web/deps.py`) redirects there, as invoicing does for `/invoicing/settings`.

### Registration

Modules are registered explicitly, in order, in the composition root, `volition/app.py`:

```python
app = create_app([invoicing.module, savings.module], PRE_MODULE_UPGRADE)
```

That's the only place that names every module. Nothing is discovered automatically.

### Dependency rules

- Core imports no module.
- Modules import from core and themselves, never from each other.
- Only the files directly in `volition/` (the composition root) may import every module.

`tests/core/test_boundaries.py` enforces this.

### Tables and migrations

Prefix every table with the slug (`invoicing_clients`, `invoicing_settings`). Each module's migrations are a tuple of SQL scripts (see `volition/invoicing/store/schema.py`). On startup, core's are applied first, then each module's in registration order, all in one transaction. The `schema_versions` table records how many of each module's scripts have run. The lists are append-only: add a new script for each change and never edit one that has been applied.
