"""The Jinja2 environment for the subscriptions module's templates (as "subscriptions/...")."""

from pathlib import Path

from volition.core.templates import environment

SLUG = "subscriptions"
TEMPLATES = Path(__file__).resolve().parent / "templates"

templates = environment({SLUG: TEMPLATES})
