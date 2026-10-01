"""Validation errors in a form the pages and API can report."""

import pydantic


class ValidationError(Exception):
    def __init__(self, what: str, errors: list[str]) -> None:
        super().__init__(f"Invalid {what}:\n  " + "\n  ".join(errors))
        self.errors = errors


def describe(err: pydantic.ValidationError) -> list[str]:
    """Pydantic errors as "<json pointer> <message>", e.g. "/lineItems/0/rate Input should be ..."."""
    messages = []
    for e in err.errors(include_url=False):
        loc = "".join(f"/{part}" for part in e["loc"]) or "(root)"
        messages.append(f"{loc} {e['msg']}")
    return messages


def validate[M: pydantic.BaseModel](model: type[M], json_text: str | bytes, what: str) -> M:
    """`model` from JSON text, or a ValidationError naming `what` was invalid."""
    try:
        return model.model_validate_json(json_text)
    except pydantic.ValidationError as e:
        raise ValidationError(what, describe(e)) from None
