"""When each subscription next renews, which renew soon, and what they all cost a month and a year."""

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from volition.core.config import timezone
from volition.subscriptions.models import Cycle, SubscriptionRecord

#: How far ahead a renewal counts as soon.
SOON = timedelta(days=30)


def today() -> date:
    """In the business's time zone."""
    return datetime.now(timezone()).date()


def _add_months(start: date, months: int) -> date:
    """`start` `months` later, on the same day or the month's last if it is shorter (31 Jan + 1 → 28 Feb)."""
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))


def next_renewal(renews_on: date, cycle: Cycle, on: date) -> date:
    """The first renewal on or after `on`: `renews_on`, or a whole number of cycles after it once it has passed.

    Counted from `renews_on` itself, so a subscription renewing on the 31st keeps the 31st where a month has it.
    """
    step = 1 if cycle == "monthly" else 12
    months = 0
    while (renewal := _add_months(renews_on, months)) < on:
        months += step
    return renewal


@dataclass(frozen=True)
class Renewal:
    subscription: SubscriptionRecord
    on: date
    #: Days from today, 0 for today; negative once a renewal by hand is overdue.
    days: int

    @property
    def soon(self) -> bool:
        """Due within SOON, or overdue."""
        return self.days <= SOON.days

    @property
    def overdue(self) -> bool:
        return self.days < 0


@dataclass(frozen=True)
class Overview:
    #: Every subscription's next renewal, soonest (or most overdue) first.
    renewals: tuple[Renewal, ...]
    #: In GBP pence: the yearly cost of everything, and that spread over 12 months.
    per_year: int
    per_month: int

    @property
    def soon(self) -> tuple[Renewal, ...]:
        return tuple(r for r in self.renewals if r.soon)

    @property
    def later(self) -> tuple[Renewal, ...]:
        return tuple(r for r in self.renewals if not r.soon)

    @property
    def soon_total(self) -> int:
        """What the renewals due soon will cost, in GBP pence."""
        return sum(r.subscription.gbp for r in self.soon)


def overview(subscriptions: Sequence[SubscriptionRecord], on: date) -> Overview:
    renewals = []
    for s in subscriptions:
        # One renewed by hand doesn't renew until someone does it, so a missed renewal stays on its date, overdue.
        when = next_renewal(s.renews_on, s.cycle, on) if s.auto_renews else s.renews_on
        renewals.append(Renewal(s, when, (when - on).days))
    renewals.sort(key=lambda r: (r.on, r.subscription.name.casefold()))
    per_year = sum(s.gbp * (12 if s.cycle == "monthly" else 1) for s in subscriptions)
    return Overview(renewals=tuple(renewals), per_year=per_year, per_month=round(per_year / 12))
