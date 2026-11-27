"""The pages: the renewal timeline (/subscriptions/), the form that adds and edits subscriptions, and the home panel."""

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from volition.core.errors import ValidationError
from volition.core.modules import NavLink
from volition.core.web.deps import FormDep
from volition.core.web.forms import FormBody, field, validate_form
from volition.core.web.shell import Shell, ShellDep
from volition.subscriptions import renewals
from volition.subscriptions.models import SubscriptionDetails, SubscriptionRecord
from volition.subscriptions.store import (
    create_subscription,
    delete_subscription,
    get_subscription,
    list_subscriptions,
    update_subscription,
)
from volition.subscriptions.templates import SLUG, templates

NAV = (NavLink("Upcoming", "/"), NavLink("New subscription", "/new"))

PREFIX = f"/{SLUG}"

SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€"}

router = APIRouter()


def money(pence: int, currency: str = "GBP") -> str:
    """e.g. "£1,234.50"."""
    return f"{SYMBOLS[currency]}{pence // 100:,}.{pence % 100:02d}"


def day_month_year(day: date) -> str:
    """e.g. "3 Dec 2026"."""
    return f"{day.day} {day:%b %Y}"


templates.filters["money"] = money
templates.filters["dmy"] = day_month_year


def _render(template: str, shell: Shell | None, **context: Any) -> str:
    return templates.get_template(f"{SLUG}/{template}").render(shell=shell, **context)


def _see_timeline() -> RedirectResponse:
    # 303 so the browser follows a form POST with a GET.
    return RedirectResponse(f"{PREFIX}/", status_code=303)


@router.get("/", response_class=HTMLResponse)
def timeline(shell: ShellDep) -> HTMLResponse:
    subscriptions = list_subscriptions()
    overview = renewals.overview(subscriptions, renewals.today())
    return HTMLResponse(_render("timeline.html", shell, overview=overview, any=bool(subscriptions)))


@router.get("/new", response_class=HTMLResponse)
def new_form(shell: ShellDep) -> HTMLResponse:
    return HTMLResponse(render_form(shell, form_values()))


@router.post("/", response_model=None)
def add(form: FormDep, shell: ShellDep) -> Response:
    try:
        create_subscription(parse_form(form))
    except ValidationError as e:
        return HTMLResponse(render_form(shell, submitted_values(form), errors=e.errors), status_code=422)
    return _see_timeline()


@router.get("/{subscription_id}", response_class=HTMLResponse)
def edit_form(subscription_id: str, shell: ShellDep) -> HTMLResponse:
    subscription = get_subscription(subscription_id)
    if subscription is None:
        raise HTTPException(404, "No such subscription")
    return HTMLResponse(render_form(shell, form_values(subscription), subscription_id))


@router.post("/{subscription_id}", response_model=None)
def save(subscription_id: str, form: FormDep, shell: ShellDep) -> Response:
    try:
        saved = update_subscription(subscription_id, parse_form(form))
    except ValidationError as e:
        html = render_form(shell, submitted_values(form), subscription_id, e.errors)
        return HTMLResponse(html, status_code=422)
    if saved is None:
        raise HTTPException(404, "No such subscription")
    return _see_timeline()


@router.post("/{subscription_id}/delete")
def remove(subscription_id: str) -> RedirectResponse:
    if not delete_subscription(subscription_id):
        raise HTTPException(404, "No such subscription")
    return _see_timeline()


def home_panel() -> str:
    """The totals and what renews soon, for the home page; nothing until there is a subscription."""
    subscriptions = list_subscriptions()
    if not subscriptions:
        return ""
    return _render("_home.html", None, overview=renewals.overview(subscriptions, renewals.today()))


def render_form(
    shell: Shell, values: dict[str, Any], subscription_id: str | None = None, errors: list[str] | None = None
) -> str:
    return _render("form.html", shell, values=values, subscription_id=subscription_id, errors=errors or [])


def _amount(pence: int | None) -> str:
    return "" if pence is None else f"{pence // 100}.{pence % 100:02d}"


def form_values(subscription: SubscriptionRecord | None = None) -> dict[str, Any]:
    """Values for the form: a stored subscription's, or blanks for a new one."""
    if subscription is None:
        return {"cycle": "monthly", "currency": "GBP", "autoRenews": True}
    return {
        "name": subscription.name,
        "vendor": subscription.vendor or "",
        "cycle": subscription.cycle,
        "renewsOn": subscription.renews_on.isoformat(),
        "currency": subscription.currency,
        "cost": _amount(subscription.cost),
        "costGbp": _amount(subscription.cost_gbp),
        "autoRenews": subscription.auto_renews,
        "paidWith": subscription.paid_with or "",
    }


_TEXT_FIELDS = ("name", "vendor", "cycle", "renewsOn", "currency", "cost", "costGbp", "paidWith")


def submitted_values(body: FormBody) -> dict[str, Any]:
    """A submission as values for re-rendering the form, e.g. alongside its errors."""
    return {**{key: field(body, key) for key in _TEXT_FIELDS}, "autoRenews": bool(field(body, "autoRenews"))}


# At most 9 digits of pounds, so the pence fit MAX_PENCE.
_AMOUNT = re.compile(r"([0-9]{1,9})(?:\.([0-9]{1,2}))?", re.ASCII)


def parse_amount(text: str, label: str, errors: list[str]) -> int | None:
    """ "12", "12.5" or "12.50" as pence, else None with a message appended to `errors`."""
    match = _AMOUNT.fullmatch(text.replace(",", ""))
    if match is None:
        errors.append(f"{label} must be an amount such as 12.50")
        return None
    return int(match[1]) * 100 + int((match[2] or "0").ljust(2, "0"))


def parse_form(body: FormBody) -> SubscriptionDetails:
    """A form submission as valid SubscriptionDetails, or raises ValidationError."""
    errors: list[str] = []
    if not field(body, "name"):
        errors.append("Name is required")
    renews_on = field(body, "renewsOn")
    try:
        date.fromisoformat(renews_on)
    except ValueError:
        errors.append("Next renewal must be a date")
    currency = field(body, "currency")
    cost = parse_amount(field(body, "cost"), "Cost", errors)
    cost_gbp = None
    if currency != "GBP":
        cost_gbp = parse_amount(field(body, "costGbp"), "Cost in GBP", errors)
    if errors:
        raise ValidationError("subscription", errors)
    subscription = {
        "name": field(body, "name"),
        "vendor": field(body, "vendor") or None,
        "cycle": field(body, "cycle"),
        "renewsOn": renews_on,
        "currency": currency,
        "cost": cost,
        "costGbp": cost_gbp,
        "autoRenews": bool(field(body, "autoRenews")),
        "paidWith": field(body, "paidWith") or None,
    }
    return validate_form(SubscriptionDetails, subscription, "subscription")
