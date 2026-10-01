"""One module per page: its routes, the values its form shows and how its submissions are parsed."""

from typing import Any

from volition.core.modules import NavLink
from volition.core.web.shell import Shell
from volition.invoicing.models import Supplier
from volition.invoicing.templates import SLUG, templates

NAV = (
    NavLink("Invoice", "/"),
    NavLink("Clients", "/clients"),
    NavLink("Defaults", "/defaults"),
    NavLink("Supplier", "/supplier"),
)


#: Where the module is mounted, for links and redirects.
PREFIX = f"/{SLUG}"


def render_page(template: str, shell: Shell, supplier: Supplier | None, **context: Any) -> str:
    """A page in base.html's frame: `shell` gives the nav, `supplier` fills the header."""
    return templates.get_template(f"{SLUG}/{template}").render(
        shell=shell,
        legal_name=supplier and supplier.legal_name,
        supplier=supplier and supplier.model_dump(by_alias=True, exclude_none=True),
        **context,
    )
