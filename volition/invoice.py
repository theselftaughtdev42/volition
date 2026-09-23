"""Pure invoice logic: models, money maths, formatting and the template view model.

Money is held in integer pence throughout. Quantities and rates are whole
numbers, and all invoices are in GBP.
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

#: UK standard rate, applied when an invoice has `vat: true`.
VAT_PERCENT = 20

Unit = Literal["days", "hours", "items"]


class Model(BaseModel):
    """camelCase JSON keys (snake_case also accepted), unknown keys rejected.

    Strict, like the JSON schemas these replace: no "10" for an int or "true" for a bool.
    Validate JSON text with `model_validate_json` (which accepts ISO date strings).
    Patterns use [0-9] because Pydantic's regex digit class also matches non-ASCII digits.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", strict=True)


class LineItem(Model):
    description: str
    detail: str | None = None
    quantity: Annotated[int, Field(ge=1)]
    #: Per unit, in whole pounds (550 = £550.00).
    rate: Annotated[int, Field(ge=0)]


class Period(Model):
    start: date
    end: date


class Client(Model):
    name: str
    contact: str | None = None
    address: Annotated[list[str], Field(min_length=1)]
    email: EmailStr | None = None


class Invoice(Model):
    number: Annotated[str, Field(pattern=r"^MS-[0-9]{4,}$")]
    issue_date: date
    #: Defaults to issue_date + supplier.payment_terms_days.
    due_date: date | None = None
    #: Service period the invoice covers; the form defaults it to the current month.
    period: Period | None = None
    vat: bool
    unit: Unit | None = None
    client: Client
    line_items: Annotated[list[LineItem], Field(min_length=1)]
    notes: str | None = None


class BankDetails(Model):
    account_name: str
    sort_code: Annotated[str, Field(pattern=r"^[0-9]{2}-[0-9]{2}-[0-9]{2}$")]
    account_number: Annotated[str, Field(pattern=r"^[0-9]{8}$")]


class Supplier(Model):
    name: str
    legal_name: str
    address: list[str]
    website: str | None = None
    email: EmailStr
    company_number: str
    registered_in: str
    vat_number: str | None = None
    payment_terms_days: Annotated[int, Field(ge=0)]
    bank: BankDetails


@dataclass(frozen=True)
class Totals:
    lines: list[int]
    subtotal: int
    vat: int
    total: int


def compute_totals(invoice: Invoice) -> Totals:
    lines = [item.quantity * item.rate * 100 for item in invoice.line_items]
    subtotal = sum(lines)
    # Integer round-half-up, matching Math.round for positive values.
    vat = (subtotal * VAT_PERCENT + 50) // 100 if invoice.vat else 0
    return Totals(lines=lines, subtotal=subtotal, vat=vat, total=subtotal + vat)


def format_invoice_number(n: int) -> str:
    return f"MS-{n:04d}"


def parse_invoice_number(number: str) -> int:
    if not (number.startswith("MS-") and number[3:].isascii() and number[3:].isdigit()):
        raise ValueError(f"Invalid invoice number: {number}")
    return int(number[3:])


def format_money(pence: int) -> str:
    """en-GB GBP, e.g. "£4,250.00", without depending on the system locale."""
    sign = "-" if pence < 0 else ""
    pounds, rem = divmod(abs(pence), 100)
    return f"{sign}£{pounds:,}.{rem:02d}"


# Spelled out rather than locale-derived: some locale data abbreviates September as "Sept".
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_day_month(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def format_date(d: date) -> str:
    """ "19 Sep 2026" """
    return f"{_format_day_month(d)} {d.year:04d}"


def format_period(start: date, end: date) -> str:
    """ "1 Sep – 30 Sep 2026", or with both years when the period spans a year end."""
    start_text = _format_day_month(start) if start.year == end.year else format_date(start)
    return f"{start_text} – {format_date(end)}"


def local_iso_date(now: datetime) -> str:
    """Today's date in the server's local time zone, as YYYY-MM-DD."""
    local = now.astimezone() if now.tzinfo else now
    return local.date().isoformat()


def month_period(today: date) -> Period:
    """First and last day of the calendar month containing `today`."""
    last_day = calendar.monthrange(today.year, today.month)[1]
    return Period(start=today.replace(day=1), end=today.replace(day=last_day))


def format_quantity(n: int) -> str:
    return f"{n:,}"


UNIT_LABELS: dict[str, str] = {"days": "Days", "hours": "Hours", "items": "Qty"}


def build_view_model(invoice: Invoice, supplier: Supplier) -> dict[str, Any]:
    """Template context. Keys stay camelCase so the templates read like the JSON."""
    totals = compute_totals(invoice)
    due_date = invoice.due_date or invoice.issue_date + timedelta(days=supplier.payment_terms_days)

    return {
        "supplier": supplier.model_dump(by_alias=True, exclude_none=True),
        "invoice": invoice.model_dump(by_alias=True, exclude_none=True),
        "fmt": {
            "issueDate": format_date(invoice.issue_date),
            "dueDate": format_date(due_date),
            "period": format_period(invoice.period.start, invoice.period.end) if invoice.period else None,
            "unitLabel": UNIT_LABELS[invoice.unit or "days"],
        },
        "lines": [
            {
                "description": item.description,
                "detail": item.detail,
                "quantity": format_quantity(item.quantity),
                "rate": format_money(item.rate * 100),
                "amount": format_money(totals.lines[i]),
            }
            for i, item in enumerate(invoice.line_items)
        ],
        "totals": {
            "subtotal": format_money(totals.subtotal),
            "vat": format_money(totals.vat) if invoice.vat else None,
            "vatPercent": f"{VAT_PERCENT}%" if invoice.vat else None,
            "total": format_money(totals.total),
        },
    }
