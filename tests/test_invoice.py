from datetime import date, datetime

from volition.invoice import (
    Invoice,
    LineItem,
    Period,
    Supplier,
    Totals,
    build_view_model,
    compute_totals,
    format_period,
    format_quantity,
    local_iso_date,
    month_period,
)


def test_example_invoice_totals_match_the_spec(invoice: Invoice, supplier: Supplier) -> None:
    vm = build_view_model(invoice, supplier)
    assert vm["totals"] == {"subtotal": "£6,325.00", "vat": "£1,265.00", "vatPercent": "20%", "total": "£7,590.00"}
    assert [(line["quantity"], line["rate"], line["amount"]) for line in vm["lines"]] == [
        ("10", "£550.00", "£5,500.00"),
        ("1", "£825.00", "£825.00"),
    ]


def test_totals_are_computed_in_integer_pence(invoice: Invoice) -> None:
    items = [LineItem(description="a", quantity=3, rate=333), LineItem(description="b", quantity=1, rate=1)]
    totals = compute_totals(invoice.model_copy(update={"line_items": items}))
    assert totals == Totals(lines=[99_900, 100], subtotal=100_000, vat=20_000, total=120_000)


def test_unticked_vat_hides_the_vat_row(invoice: Invoice, supplier: Supplier) -> None:
    vm = build_view_model(invoice.model_copy(update={"vat": False}), supplier)
    assert vm["totals"]["vat"] is None
    assert vm["totals"]["total"] == "£6,325.00"


def test_dates_due_date_default_and_period_formatting(invoice: Invoice, supplier: Supplier) -> None:
    period = Period(start=date(2026, 9, 1), end=date(2026, 9, 30))
    vm = build_view_model(invoice.model_copy(update={"due_date": None, "period": period}), supplier)
    assert vm["fmt"]["issueDate"] == "19 Sep 2026"
    assert vm["fmt"]["dueDate"] == "19 Oct 2026"
    assert vm["fmt"]["period"] == "1 Sep – 30 Sep 2026"
    assert format_period(date(2026, 12, 15), date(2027, 1, 14)) == "15 Dec 2026 – 14 Jan 2027"


def test_default_period_is_the_whole_current_month() -> None:
    assert month_period(date(2026, 9, 23)) == Period(start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert month_period(date(2026, 1, 31)) == Period(start=date(2026, 1, 1), end=date(2026, 1, 31))
    assert month_period(date(2028, 2, 10)) == Period(start=date(2028, 2, 1), end=date(2028, 2, 29))
    assert local_iso_date(datetime(2026, 9, 23, 23, 59)) == "2026-09-23"


def test_quantities_are_grouped() -> None:
    assert [format_quantity(n) for n in (1, 10, 1500)] == ["1", "10", "1,500"]
