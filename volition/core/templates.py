"""Jinja2 environments: the shell's templates (base.html) plus module templates under their slug."""

from collections.abc import Mapping
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PrefixLoader

TEMPLATES = Path(__file__).resolve().parent / "templates"


def environment(namespaces: Mapping[str, Path]) -> Environment:
    """The shell's templates, plus each directory in `namespaces` under its key, e.g. "invoicing/form.html"."""
    return Environment(
        loader=ChoiceLoader(
            [
                FileSystemLoader(TEMPLATES),
                PrefixLoader({slug: FileSystemLoader(path) for slug, path in namespaces.items()}),
            ]
        ),
        autoescape=True,
        # Drop whole lines holding only a block tag, as Handlebars does for standalone tags.
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        # Absent optional values print nothing, as in Handlebars.
        finalize=lambda value: "" if value is None else value,
    )


#: The shell's own pages.
templates = environment({})
