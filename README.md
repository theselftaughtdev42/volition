# volition

Invoice generator for Mackay Software: a small web form that produces a branded A4 PDF for a client chosen from a list.

## Setup

Requires Python 3.14, [uv](https://docs.astral.sh/uv/) and Pango, which [WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) renders PDFs with (`brew install pango`, or `apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`).

```sh
make install
make start      # http://127.0.0.1:3000, honours HOST and PORT
```

Also: `make dev`, `make test`, `make lint`, `make format`.

## Docker

The image listens on port 3000 and keeps its database (supplier, defaults, clients and the invoice counter) in `/data`. Mount it: the database holds bank details and is never baked into the image.

```sh
make docker.build && make docker.run    # mounts ./data
```

Pushing a `v*` tag publishes `ghcr.io/theselftaughtdev42/volition` (see `.github/workflows/publish.yml`). `GET /health` backs the container healthcheck.

To cut a release, run `make release BUMP=patch` (or `minor`/`major`, or `V=1.2.3`) from a clean `main` that matches `origin/main`. It runs lint and tests, bumps the version in `pyproject.toml` and `uv.lock`, commits, tags `vX.Y.Z` and asks before pushing.

## Configuration

Everything lives in the database. On the first run every page redirects to ask for it:

1. `/supplier`: who invoices are from. The trading and legal names, address, email, website, company number and where it is registered, VAT number, payment terms and bank details, all printed on each invoice.
2. `/defaults`: the invoice defaults. The first invoice number, whether VAT is ticked, unit, line items (description, detail, rate), and notes. They are used where the chosen client sets none.

Both can be changed on those pages later.

There is no login, so anyone who can reach the port can use the app. Form posts from other websites are rejected (by `Sec-Fetch-Site`, else `Origin`), so a page you visit can't change the bank details behind your back, and requests for hostnames outside `ALLOWED_HOSTS` are refused.

Invoice numbers are `MS-` plus a zero-padded integer. The form suggests the next one: the first invoice number from the defaults, then the last generated number + 1. The number can be overridden; regenerating an older invoice never winds the counter back. Raising the first invoice number above the counter jumps ahead.

The period defaults to the current calendar month, the issue date to today, and the due date (if left blank) to issue date + `paymentTermsDays`.

## Clients

Clients are managed at `/clients` and stored in `DATA_DIR/volition.db`. Each has bill-to details (name, contact, address, email) and optional invoice defaults: VAT, unit, line items (description, detail and rate; quantities are entered per invoice) and notes. Anything a client leaves unset falls back to the defaults.

The invoice form bills whichever client is chosen from its dropdown, exactly as stored: fix a client's details on its page rather than on the invoice. Choosing a client replaces the VAT, unit, line items and notes with that client's defaults. A lone client is preselected; with several, one must be chosen. Names are unique, ignoring case, and client ids are UUIDv7s.

The schema is migrated on startup (see `MIGRATIONS` in `volition/db.py`, tracked by `PRAGMA user_version`).

## Environment

| Variable | Default | |
| --- | --- | --- |
| `PORT` | `3000` | Used by `python -m volition` (and `fastapi dev`/`run`, whose own default is 8000). |
| `HOST` | `127.0.0.1` | Used by `python -m volition`. Set `0.0.0.0` to listen beyond localhost. |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,[::1]` | Comma-separated hostnames the app answers to; other `Host` headers get a 400 (guarding against DNS rebinding). Add yours when serving under a domain name or LAN address, or `*` to allow any. Read at startup. |
| `DATA_DIR` | `./data` | Holds `volition.db` (SQLite: supplier, defaults, clients and the last invoice number). Persist it across deploys. |

## Invoice rules

- Everything is in GBP. Quantities and rates are whole numbers (rates in whole pounds); money is integer pence internally.
- `lineTotal = quantity × rate`; `vat = subtotal × 20%` (`VAT_PERCENT` in `volition/invoice.py`) when the VAT box is ticked; `total = subtotal + vat`.
- Unticked VAT hides the VAT row and the VAT number.
- Dates print as `19 Sep 2026`, the period as `1 Sep – 30 Sep 2026`, money as `£4,250.00`.
- Long invoices continue onto further pages with the table header repeated; the totals block never splits.
