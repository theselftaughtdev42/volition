"""The model base every module's stored and validated data shares, and the business, which every module can use."""

from pydantic import BaseModel, ConfigDict, EmailStr
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    """camelCase JSON keys (snake_case also accepted), unknown keys rejected.

    Strict, like the JSON schemas these replace: no "10" for an int or "true" for a bool.
    Validate JSON text with `model_validate_json` (which accepts ISO date strings).
    Patterns use [0-9] because Pydantic's regex digit class also matches non-ASCII digits.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", strict=True)


class Business(Model):
    """Who the app belongs to: the company's identity, as printed on what modules produce (e.g. invoices)."""

    #: The trading name.
    name: str
    legal_name: str
    address: list[str]
    website: str | None = None
    email: EmailStr
    company_number: str
    registered_in: str
    vat_number: str | None = None
