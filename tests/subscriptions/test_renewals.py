from datetime import date, datetime

import pytest

from volition.subscriptions import renewals
from volition.subscriptions.models import SubscriptionRecord
from volition.subscriptions.renewals import next_renewal, overview
from volition.subscriptions.renewals import today as real_today  # before the conftest fixes it


def sub(name: str, cycle: str, renews_on: date, pence: int, **extra: object) -> SubscriptionRecord:
    return SubscriptionRecord.model_validate(
        {
            "id": name,
            "name": name,
            "cycle": cycle,
            "renewsOn": renews_on.isoformat(),
            "currency": "GBP",
            "cost": pence,
            "autoRenews": True,
            **extra,
        },
        strict=False,
    )


@pytest.mark.parametrize(
    ("renews_on", "cycle", "on", "expected"),
    [
        # Not yet passed: as entered.
        (date(2026, 12, 3), "monthly", date(2026, 11, 27), date(2026, 12, 3)),
        # Today counts.
        (date(2026, 11, 27), "monthly", date(2026, 11, 27), date(2026, 11, 27)),
        # Passed: rolls on by whole cycles, across a year end.
        (date(2026, 10, 3), "monthly", date(2027, 1, 4), date(2027, 2, 3)),
        (date(2024, 6, 11), "yearly", date(2026, 11, 27), date(2027, 6, 11)),
        # The 31st keeps the 31st where a month has it and the last day where it doesn't.
        (date(2026, 1, 31), "monthly", date(2026, 2, 2), date(2026, 2, 28)),
        (date(2026, 1, 31), "monthly", date(2026, 3, 1), date(2026, 3, 31)),
        (date(2024, 2, 29), "yearly", date(2025, 1, 1), date(2025, 2, 28)),
    ],
)
def test_next_renewal(renews_on: date, cycle: str, on: date, expected: date) -> None:
    assert next_renewal(renews_on, cycle, on) == expected  # ty: ignore[invalid-argument-type]


def test_the_overview_orders_renewals_and_totals_in_gbp() -> None:
    today = date(2026, 11, 27)
    subs = [
        sub("domain", "yearly", date(2026, 12, 20), 850, autoRenews=False),
        sub("Claude", "monthly", date(2026, 12, 3), 2000, currency="USD", costGbp=1600),
        sub("vps", "monthly", date(2027, 1, 1), 390),
        sub("Office", "monthly", date(2026, 12, 3), 1030),
    ]
    result = overview(subs, today)
    assert [(r.subscription.name, r.days) for r in result.renewals] == [
        ("Claude", 6),
        ("Office", 6),
        ("domain", 23),
        ("vps", 35),
    ]
    assert [r.subscription.name for r in result.soon] == ["Claude", "Office", "domain"]
    assert [r.subscription.name for r in result.later] == ["vps"]
    assert result.soon_total == 1600 + 1030 + 850
    assert result.per_year == (1600 + 1030 + 390) * 12 + 850
    assert result.per_month == round(result.per_year / 12)


def test_thirty_days_out_is_soon_and_thirty_one_is_not() -> None:
    today = date(2026, 11, 27)
    result = overview([sub("a", "yearly", date(2026, 12, 27), 1), sub("b", "yearly", date(2026, 12, 28), 1)], today)
    assert [r.soon for r in result.renewals] == [True, False]


def test_an_empty_overview() -> None:
    result = overview([], date(2026, 11, 27))
    assert (result.renewals, result.per_year, result.per_month, result.soon_total) == ((), 0, 0, 0)


def test_today_is_in_the_business_time_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Pacific/Auckland")
    assert real_today() == datetime.now(renewals.timezone()).date()
