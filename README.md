# volition

Invoice generator for Mackay Software: a small web form that produces a branded A4 PDF.

## Setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
make install    # add --with-deps to the playwright step on a fresh Linux server
cp config/supplier.example.json config/supplier.json
cp config/defaults.example.json config/defaults.json
# edit both files, then:
make start      # http://127.0.0.1:3000, honours HOST and PORT
```

Also: `make dev`, `make test`, `make lint`, `make format`.

## Docker

The image bundles Chromium and listens on port 3000, reading config from `/config` and keeping the counter in `/data`. Mount both: config holds bank details and is never baked into the image.

```sh
make docker.build && make docker.run    # mounts ./config read-only and ./data
```

Pushing a `v*` tag publishes `ghcr.io/theselftaughtdev42/volition` (see `.github/workflows/publish.yml`). `GET /health` backs the container healthcheck.

To cut a release, run `make release BUMP=patch` (or `minor`/`major`, or `V=1.2.3`) from a clean `main` that matches `origin/main`. It runs lint and tests, bumps the version in `pyproject.toml` and `uv.lock`, commits, tags `vX.Y.Z` and asks before pushing.

## Configuration

Both config files are validated against the Pydantic models in `volition/` (`Supplier` in `invoice.py`, `Defaults` in `config.py`) at startup and on every request, so edits apply without a restart.

| File | Contents |
| --- | --- |
| `config/supplier.json` | Company, address, registration, bank details, payment terms. Not editable from the form. |
| `config/defaults.json` | Form defaults: client, whether VAT is ticked, unit, line items, notes, and `invoiceNumberStart`. |

Invoice numbers are `MS-` plus a zero-padded integer. The form suggests the next one: `invoiceNumberStart` for the first invoice, then the last generated number + 1 (stored in `data/state.json`). The number can be overridden; regenerating an older invoice never winds the counter back. Raising `invoiceNumberStart` above the counter jumps ahead.

The period defaults to the current calendar month, the issue date to today, and the due date (if left blank) to issue date + `paymentTermsDays`.

## Environment

| Variable | Default | |
| --- | --- | --- |
| `PORT` | `3000` | Used by `python -m volition` (and `fastapi dev`/`run`, whose own default is 8000). |
| `HOST` | `127.0.0.1` | Used by `python -m volition`. Set `0.0.0.0` to listen beyond localhost. |
| `CONFIG_DIR` | `./config` | |
| `DATA_DIR` | `./data` | Holds `state.json` (last invoice number). Persist it across deploys. |

## Invoice rules

- Everything is in GBP. Quantities and rates are whole numbers (rates in whole pounds); money is integer pence internally.
- `lineTotal = quantity × rate`; `vat = subtotal × 20%` (`VAT_PERCENT` in `volition/invoice.py`) when the VAT box is ticked; `total = subtotal + vat`.
- Unticked VAT hides the VAT row and the VAT number.
- Dates print as `19 Sep 2026`, the period as `1 Sep – 30 Sep 2026`, money as `£4,250.00`.
- Long invoices continue onto further pages with the table header repeated; the totals block never splits.
