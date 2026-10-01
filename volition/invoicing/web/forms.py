"""Reading the preset line items the client and defaults forms share."""

from typing import Any

from volition.core.web.forms import FormBody, field_values, whole_number


def submitted_preset_lines(body: FormBody) -> list[dict[str, str]]:
    """The preset line item rows (no quantity) of a client or defaults form, as submitted."""
    rows = zip(
        field_values(body, "description"), field_values(body, "detail"), field_values(body, "rate"), strict=False
    )
    return [{"description": d, "detail": dt, "rate": r} for d, dt, r in rows] or [{}]


def parse_preset_lines(body: FormBody, errors: list[str]) -> list[dict[str, Any]]:
    """Preset line items (no quantity), skipping blank rows."""
    line_items = []
    for i, row in enumerate(r for r in submitted_preset_lines(body) if any(r.values())):
        label = f"Line {i + 1}"
        if not row["description"]:
            errors.append(f"{label}: description is required")
        rate = whole_number(row["rate"], f"{label}: rate", 0, errors) if row["rate"] else None
        line_items.append({"description": row["description"], "detail": row["detail"] or None, "rate": rate})
    return line_items
