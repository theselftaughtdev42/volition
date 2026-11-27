import uuid
from datetime import date

import pytest

from volition.core.errors import ValidationError, validate
from volition.subscriptions.models import SubscriptionDetails
from volition.subscriptions.store import (
    create_subscription,
    delete_subscription,
    get_subscription,
    list_subscriptions,
    update_subscription,
)

CLAUDE = SubscriptionDetails(
    name="Claude Pro",
    vendor="Anthropic",
    cycle="monthly",
    renews_on=date(2026, 12, 3),
    currency="USD",
    cost=2000,
    cost_gbp=1600,
    auto_renews=True,
    paid_with="Business Visa",
)
DOMAIN = SubscriptionDetails(
    name="example.co.uk", cycle="yearly", renews_on=date(2026, 12, 20), currency="GBP", cost=850, auto_renews=False
)


def test_a_created_subscription_round_trips_with_a_uuid7_id() -> None:
    created = create_subscription(CLAUDE)
    assert uuid.UUID(created.id).version == 7
    assert get_subscription(created.id) == created
    assert created.model_dump(exclude={"id"}) == CLAUDE.model_dump()
    assert created.gbp == 1600


def test_subscriptions_list_alphabetically_ignoring_case() -> None:
    for name in ["zeta", "Beta", "alpha"]:
        create_subscription(DOMAIN.model_copy(update={"name": name}))
    assert [s.name for s in list_subscriptions()] == ["alpha", "Beta", "zeta"]


def test_updating_replaces_every_field() -> None:
    created = create_subscription(CLAUDE)
    updated = update_subscription(created.id, DOMAIN)
    assert updated is not None
    assert get_subscription(created.id) == updated
    assert (updated.name, updated.cost_gbp, updated.vendor, updated.gbp) == ("example.co.uk", None, None, 850)


def test_updating_or_deleting_a_missing_subscription_says_so() -> None:
    assert update_subscription("nope", CLAUDE) is None
    assert delete_subscription("nope") is False
    assert get_subscription("nope") is None


def test_deleting_a_subscription() -> None:
    created = create_subscription(CLAUDE)
    assert delete_subscription(created.id) is True
    assert list_subscriptions() == []


@pytest.mark.parametrize(
    ("currency", "cost_gbp", "message"),
    [
        ("GBP", 100, "costGbp is only for a currency other than GBP"),
        ("EUR", None, "costGbp is required for a currency other than GBP"),
    ],
)
def test_the_gbp_cost_goes_with_another_currency_only(currency: str, cost_gbp: int | None, message: str) -> None:
    data = DOMAIN.model_dump_json(by_alias=True, exclude={"currency", "cost_gbp"})
    extra = f', "currency": "{currency}"' + ("" if cost_gbp is None else f', "costGbp": {cost_gbp}')
    with pytest.raises(ValidationError) as exc:
        validate(SubscriptionDetails, data[:-1] + extra + "}", "subscription")
    assert message in exc.value.errors[0]
