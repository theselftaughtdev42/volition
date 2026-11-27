import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.subscriptions.test_store import CLAUDE, DOMAIN
from volition.subscriptions.store import create_subscription, get_subscription, list_subscriptions
from volition.subscriptions.web import day_month_year, money, parse_amount

FORM: dict[str, str] = {
    "name": "Claude Pro",
    "vendor": "Anthropic",
    "cycle": "monthly",
    "renewsOn": "2026-12-03",
    "currency": "USD",
    "cost": "20",
    "costGbp": "16.00",
    "autoRenews": "yes",
    "paidWith": "Business Visa",
}


def errors(html: str) -> list[str]:
    return re.findall(r"<li>(.*?)</li>", html)


# --- Formatting and parsing ---


def test_money_and_dates_format_for_people() -> None:
    assert money(123450) == "£1,234.50"
    assert money(5, "USD") == "$0.05"
    assert money(2000, "EUR") == "€20.00"
    assert day_month_year(date(2027, 1, 8)) == "8 Jan 2027"


@pytest.mark.parametrize(
    ("text", "pence"),
    [("12", 1200), ("12.5", 1250), ("12.05", 1205), ("1,234.50", 123450), ("999,999,999.99", 99_999_999_999)],
)
def test_amounts_parse_to_pence(text: str, pence: int) -> None:
    found: list[str] = []
    assert parse_amount(text, "Cost", found) == pence
    assert found == []


@pytest.mark.parametrize("text", ["", "abc", "-1", "1.234", "1e3", "1000000000", "9" * 5000])
def test_other_amounts_are_errors(text: str) -> None:
    found: list[str] = []
    assert parse_amount(text, "Cost", found) is None
    assert found == ["Cost must be an amount such as 12.50"]


# --- Timeline ---


def test_without_subscriptions_the_timeline_asks_for_one(client: TestClient) -> None:
    page = client.get("/subscriptions/").text
    assert "No subscriptions yet." in page
    assert 'href="/subscriptions/new"' in page
    assert "Per month" not in page


def test_the_timeline_splits_soon_from_later_with_totals(client: TestClient) -> None:
    create_subscription(CLAUDE)
    create_subscription(DOMAIN)
    later = {"name": "later.dev", "renews_on": date(2027, 6, 11), "paid_with": "Amex"}
    create_subscription(DOMAIN.model_copy(update=later))
    page = client.get("/subscriptions/").text
    figures = re.findall(r'<span class="figure">(.*?)</span>', page)
    assert figures == ["£17.42", "£209.00", "2 · £24.50"]
    soon, later = page.split("<h2>Later</h2>")
    assert soon.index("Claude Pro") < soon.index("example.co.uk")
    assert "Anthropic · Monthly · Business Visa" in soon
    assert "Auto-renews in 6 days" in soon
    assert '<li class="renewal manual">' in soon
    assert "Renew by hand within 23 days" in soon
    assert "$20.00" in soon
    assert "later.dev" in later
    assert "11 Jun 2027" in later
    assert "Yearly · Amex" in later


def test_renewals_today_and_tomorrow_say_so(client: TestClient) -> None:
    create_subscription(DOMAIN.model_copy(update={"renews_on": date(2026, 11, 27)}))
    create_subscription(CLAUDE.model_copy(update={"renews_on": date(2026, 11, 27)}))
    create_subscription(CLAUDE.model_copy(update={"name": "Tomorrow", "renews_on": date(2026, 11, 28)}))
    create_subscription(DOMAIN.model_copy(update={"name": "Manual tomorrow", "renews_on": date(2026, 11, 28)}))
    page = client.get("/subscriptions/").text
    assert "Renew by hand today" in page
    assert "Auto-renews today" in page
    assert "Auto-renews in 1 day<" in page
    assert "Renew by hand within 1 day<" in page
    assert "<h2>Later</h2>" not in page


def test_a_missed_renewal_by_hand_stays_overdue(client: TestClient) -> None:
    create_subscription(DOMAIN.model_copy(update={"renews_on": date(2026, 11, 20)}))
    create_subscription(DOMAIN.model_copy(update={"name": "Yesterday", "renews_on": date(2026, 11, 26)}))
    create_subscription(CLAUDE.model_copy(update={"renews_on": date(2026, 11, 20)}))
    page = client.get("/subscriptions/").text
    assert "Renewal by hand overdue by 7 days" in page
    assert "Renewal by hand overdue by 1 day<" in page
    assert "Auto-renews in 23 days" in page
    assert "<h2>Later</h2>" not in page
    assert '<span class="badge warn">Overdue</span>' in client.get("/").text


def test_with_nothing_due_soon_the_timeline_says_so(client: TestClient) -> None:
    create_subscription(DOMAIN.model_copy(update={"renews_on": date(2027, 6, 11)}))
    assert "Nothing renews in the next 30 days." in client.get("/subscriptions/").text


# --- Home panel ---


def test_the_home_page_has_no_panel_until_there_is_a_subscription(client: TestClient) -> None:
    assert "Subscriptions per month" not in client.get("/").text


def test_the_home_page_shows_the_totals_and_what_renews_soon(client: TestClient) -> None:
    claude = create_subscription(CLAUDE)
    create_subscription(DOMAIN)
    page = client.get("/").text
    assert "Subscriptions per month" in page
    assert "Subscriptions per year" in page
    assert re.findall(r'<span class="figure">(.*?)</span>', page) == ["£16.71", "£200.50", "2 · £24.50"]
    assert f'<a class="what" href="/subscriptions/{claude.id}">Claude Pro</a>' in page
    assert '<span class="badge warn">Renew by hand</span>' in page
    # Above the module cards.
    assert page.index("Renewing in the next 30 days") < page.index('<a class="card"')


def test_the_home_panel_leaves_out_the_list_when_nothing_is_due(client: TestClient) -> None:
    create_subscription(DOMAIN.model_copy(update={"renews_on": date(2027, 6, 11)}))
    page = client.get("/").text
    assert "Subscriptions per month" in page
    assert "Renewing in the next 30 days" not in page


# --- Form ---


def test_new_subscription_form(client: TestClient) -> None:
    page = client.get("/subscriptions/new").text
    assert '<form id="subscription" method="post" action="/subscriptions/">' in page
    assert '<option value="monthly" selected>Monthly</option>' in page
    assert '<option value="GBP" selected>GBP</option>' in page
    assert 'name="autoRenews" type="checkbox" value="yes" checked' in page
    assert "Delete" not in page


def test_adding_a_subscription_redirects_to_the_timeline(client: TestClient) -> None:
    res = client.post("/subscriptions/", data=FORM, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/subscriptions/"
    [stored] = list_subscriptions()
    assert stored.model_dump(exclude={"id"}) == CLAUDE.model_dump()


def test_blank_optional_fields_and_gbp_ignore_the_gbp_cost(client: TestClient) -> None:
    body = {**FORM, "vendor": "", "paidWith": "", "currency": "GBP", "cost": "8.5", "costGbp": "999"}
    del body["autoRenews"]
    assert client.post("/subscriptions/", data=body, follow_redirects=False).status_code == 303
    [stored] = list_subscriptions()
    assert (stored.vendor, stored.paid_with, stored.cost, stored.cost_gbp, stored.auto_renews) == (
        None,
        None,
        850,
        None,
        False,
    )


def test_an_invalid_form_is_re_rendered_with_its_errors_and_values(client: TestClient) -> None:
    body = {**FORM, "name": "", "renewsOn": "soon", "cost": "abc", "costGbp": ""}
    del body["autoRenews"]
    res = client.post("/subscriptions/", data=body)
    assert res.status_code == 422
    assert errors(res.text) == [
        "Name is required",
        "Next renewal must be a date",
        "Cost must be an amount such as 12.50",
        "Cost in GBP must be an amount such as 12.50",
    ]
    assert 'value="Anthropic"' in res.text
    assert 'value="soon"' in res.text
    assert 'value="yes" checked' not in res.text
    assert list_subscriptions() == []


def test_an_amount_too_large_is_a_form_error_not_a_crash(client: TestClient) -> None:
    res = client.post("/subscriptions/", data={**FORM, "costGbp": "99999999999999999999"})
    assert res.status_code == 422
    assert errors(res.text) == ["Cost in GBP must be an amount such as 12.50"]


def test_schema_errors_on_the_form_are_reported(client: TestClient) -> None:
    res = client.post("/subscriptions/", data={**FORM, "cycle": "weekly"})
    assert res.status_code == 422
    assert re.findall(r"<li>(/\w+) ", res.text) == ["/cycle"]


def test_editing_a_subscription(client: TestClient) -> None:
    stored = create_subscription(CLAUDE)
    page = client.get(f"/subscriptions/{stored.id}").text
    assert '<h1 class="page-title">Claude Pro</h1>' in page
    assert 'value="20.00"' in page
    assert 'value="16.00"' in page
    assert 'value="2026-12-03"' in page
    assert '<option value="USD" selected>USD</option>' in page
    assert f'action="/subscriptions/{stored.id}/delete"' in page

    res = client.post(f"/subscriptions/{stored.id}", data={**FORM, "name": "Claude Max"}, follow_redirects=False)
    assert res.status_code == 303
    edited = get_subscription(stored.id)
    assert edited is not None
    assert edited.name == "Claude Max"


def test_editing_a_gbp_subscription_leaves_the_gbp_cost_blank(client: TestClient) -> None:
    stored = create_subscription(DOMAIN)
    page = client.get(f"/subscriptions/{stored.id}").text
    assert 'name="costGbp" type="number" min="0" step="0.01" value=""' in page
    assert 'value="yes" checked' not in page


def test_an_invalid_edit_is_re_rendered_and_leaves_the_subscription_unchanged(client: TestClient) -> None:
    stored = create_subscription(CLAUDE)
    res = client.post(f"/subscriptions/{stored.id}", data={**FORM, "name": ""})
    assert res.status_code == 422
    assert errors(res.text) == ["Name is required"]
    assert f'action="/subscriptions/{stored.id}/delete"' in res.text
    assert get_subscription(stored.id) == stored


def test_deleting_a_subscription(client: TestClient) -> None:
    stored = create_subscription(CLAUDE)
    res = client.post(f"/subscriptions/{stored.id}/delete", follow_redirects=False)
    assert res.status_code == 303
    assert list_subscriptions() == []


def test_missing_subscriptions_are_404s(client: TestClient) -> None:
    assert client.get("/subscriptions/nope").status_code == 404
    assert client.post("/subscriptions/nope", data=FORM).status_code == 404
    assert client.post("/subscriptions/nope/delete").status_code == 404


def test_the_nav_marks_the_page(client: TestClient) -> None:
    assert '<a href="/subscriptions/" aria-current="page">Upcoming</a>' in client.get("/subscriptions/").text
    page = client.get("/subscriptions/new").text
    assert '<a href="/subscriptions/new" aria-current="page">New subscription</a>' in page
