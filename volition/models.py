"""Every model the app validates, stores or renders: invoices, the supplier, clients and the invoice defaults.

Money is held in integer pence throughout. Quantities and rates are whole
numbers, and all invoices are in GBP.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

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
    """Who an invoice is billed to, as printed on it."""

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
    #: The bank itself, e.g. "Monzo".
    bank_name: str
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


class PresetLineItem(Model):
    """A line an invoice starts with, from a client or the defaults. Quantities vary per invoice, so there is none here."""

    description: Annotated[str, Field(min_length=1)]
    detail: str | None = None
    rate: Annotated[int, Field(ge=0)] | None = None


class ClientDetails(Model):
    """Everything about a client that the client form edits."""

    name: Annotated[str, Field(min_length=1)]
    contact: str | None = None
    address: Annotated[list[str], Field(min_length=1)]
    email: EmailStr | None = None
    #: Invoice defaults for this client; None falls back to the global defaults.
    vat: bool | None = None
    unit: Unit | None = None
    line_items: list[PresetLineItem] = []
    notes: str | None = None

    def bill_to(self) -> Client:
        return Client(name=self.name, contact=self.contact, address=self.address, email=self.email)


class ClientRecord(ClientDetails):
    #: A UUIDv7, as text.
    id: str


class Defaults(Model):
    """Pre-filled values for the invoice form, used where the chosen client sets none.

    Everything can be overridden per invoice.
    """

    #: Number used when no invoice has been generated yet (1 → MS-0001).
    invoice_number_start: Annotated[int, Field(ge=1)]
    #: Whether the VAT box starts ticked.
    vat: bool
    unit: Unit
    line_items: list[PresetLineItem] = []
    notes: str | None = None
