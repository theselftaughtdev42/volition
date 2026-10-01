"""One module per page: its routes, the values its form shows and how its submissions are parsed."""

from typing import Any

from volition.core.modules import NavLink
from volition.core.web.shell import Shell
from volition.invoicing.templates import SLUG, templates

NAV = (
    NavLink("Invoice", "/"),
    NavLink("Clients", "/clients"),
    NavLink("Settings", "/settings"),
)


#: Where the module is mounted, for links and redirects.
PREFIX = f"/{SLUG}"


def render_page(template: str, shell: Shell, **context: Any) -> str:
    """A page in base.html's frame, which `shell` fills in."""
    return templates.get_template(f"{SLUG}/{template}").render(shell=shell, **context)
