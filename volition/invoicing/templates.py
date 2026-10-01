"""The Jinja2 environment for invoicing's templates (as "invoicing/..."): its pages and the invoice itself."""

from pathlib import Path

from volition.core.templates import environment

SLUG = "invoicing"
TEMPLATES = Path(__file__).resolve().parent / "templates"

templates = environment({SLUG: TEMPLATES})
