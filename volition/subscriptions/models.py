"""What the business pays for on a cycle: subscriptions, and the totals and renewals worked out from them.

Money is held in integer pence. Totals are in GBP: a subscription billed in another currency also carries what it
costs in GBP, as entered (there are no exchange rates).
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from volition.core.models import Model

Cycle = Literal["monthly", "yearly"]
Currency = Literal["GBP", "USD", "EUR"]

Pence = Annotated[int, Field(ge=0)]


class SubscriptionDetails(Model):
    """Everything the subscription form edits."""

    name: Annotated[str, Field(min_length=1)]
    vendor: str | None = None
    cycle: Cycle
    #: The next renewal as entered. Once it passes, renewals roll on by the cycle (see renewals.next_renewal).
    renews_on: date
    currency: Currency
    #: Per cycle, in `currency`.
    cost: Pence
    #: Per cycle, in GBP; only for another currency.
    cost_gbp: Pence | None = None
    auto_renews: bool
    #: The card or account it is paid with, e.g. "Business Visa".
    paid_with: str | None = None

    @model_validator(mode="after")
    def _gbp_cost_matches_currency(self) -> Self:
        if self.currency == "GBP" and self.cost_gbp is not None:
            raise ValueError("costGbp is only for a currency other than GBP")
        if self.currency != "GBP" and self.cost_gbp is None:
            raise ValueError("costGbp is required for a currency other than GBP")
        return self

    @property
    def gbp(self) -> int:
        """Per cycle, in GBP pence."""
        return self.cost if self.cost_gbp is None else self.cost_gbp


class SubscriptionRecord(SubscriptionDetails):
    #: A UUIDv7, as text.
    id: str
