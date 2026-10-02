"""Every model invoicing validates, stores or renders: invoices, clients and the invoicing settings.

Money is held in integer pence throughout. Quantities and rates are whole
numbers, and all invoices are in GBP.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import EmailStr, Field

from volition.core.models import Model

Unit = Literal["days", "hours", "items"]


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
    #: Defaults to issue_date + settings.payment_terms_days.
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


class PresetLineItem(Model):
    """A line an invoice starts with, from a client or the settings' defaults.

    Quantities vary per invoice, so there is none here.
    """

    description: Annotated[str, Field(min_length=1)]
    detail: str | None = None
    rate: Annotated[int, Field(ge=0)] | None = None


class ClientDetails(Model):
    """Everything about a client that the client form edits."""

    name: Annotated[str, Field(min_length=1)]
    contact: str | None = None
    address: Annotated[list[str], Field(min_length=1)]
    email: EmailStr | None = None
    #: Invoice defaults for this client; None falls back to the settings' defaults.
    vat: bool | None = None
    unit: Unit | None = None
    line_items: list[PresetLineItem] = Field(default_factory=list)
    notes: str | None = None

    def bill_to(self) -> Client:
        return Client(name=self.name, contact=self.contact, address=self.address, email=self.email)


class ClientRecord(ClientDetails):
    #: A UUIDv7, as text.
    id: str


class InvoicingSettings(Model):
    """Everything invoices need beyond the business: the invoice form's defaults, payment terms and bank details.

    The defaults pre-fill the invoice form where the chosen client sets none, and can be overridden per invoice.
    """

    #: Number used when no invoice has been generated yet (1 → MS-0001).
    invoice_number_start: Annotated[int, Field(ge=1)]
    #: Whether the VAT box starts ticked.
    vat: bool
    unit: Unit
    line_items: list[PresetLineItem] = Field(default_factory=list)
    notes: str | None = None
    payment_terms_days: Annotated[int, Field(ge=0)]
    #: Where invoices ask to be paid.
    bank: BankDetails
