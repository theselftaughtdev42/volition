"""Reading form submissions: fields, whole numbers and lines, and validating the result against a model."""

import json
import math
import re
from typing import Any, Protocol

import pydantic

from volition.core.errors import validate


class FormBody(Protocol):
    """Starlette's FormData, or anything else with a multi-value `getlist`."""

    def getlist(self, key: str) -> list[Any]: ...


def field_values(body: FormBody, key: str) -> list[str]:
    """Every value submitted under `key`, trimmed."""
    # Uploaded files are not expected anywhere in the form; treat them as blank.
    return [value.strip() if isinstance(value, str) else "" for value in body.getlist(key)]


def field(body: FormBody, key: str) -> str:
    """The first value submitted under `key`, trimmed, or "" if there is none."""
    values = field_values(body, key)
    return values[0] if values else ""


# What JavaScript's Number() accepts once trimmed (browsers only ever send the decimal form).
_JS_DECIMAL = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
_JS_RADIX = re.compile(r"0(?:[xX][0-9a-fA-F]+|[oO][0-7]+|[bB][01]+)", re.ASCII)


def whole_number(value: str, label: str, minimum: int, errors: list[str]) -> int | None:
    """`value` as an int of at least `minimum`, else None with a message appended to `errors`."""
    n: float | None = None
    if _JS_DECIMAL.fullmatch(value):
        n = float(value)
    elif _JS_RADIX.fullmatch(value):
        n = int(value, 0)
    if n is None or not math.isfinite(n) or n != int(n) or n < minimum:
        errors.append(f"{label} must be a whole number of {minimum} or more")
        return None
    return int(n)


def lines(text: str) -> list[str]:
    """The non-blank lines of a textarea, trimmed."""
    return [line.strip() for line in text.split("\n") if line.strip()]


def drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_none(v) for v in value]
    return value


def validate_form[M: pydantic.BaseModel](model: type[M], data: dict[str, Any], what: str) -> M:
    """Drops absent optional keys, then validates as JSON exactly as stored data would be."""
    return validate(model, json.dumps(drop_none(data)), what)
