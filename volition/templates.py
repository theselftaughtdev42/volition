"""The Jinja2 environment for everything in templates/: the web pages and the invoice itself."""

from jinja2 import Environment, FileSystemLoader

from volition.config import ROOT

templates = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=True,
    # Drop whole lines holding only a block tag, as Handlebars does for standalone tags.
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    # Absent optional values print nothing, as in Handlebars.
    finalize=lambda value: "" if value is None else value,
)
