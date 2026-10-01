"""One module per page: its routes, the values its form shows and how its submissions are parsed."""

from typing import Any

from volition.models import Supplier
from volition.templates import templates


def render_page(template: str, page: str, supplier: Supplier | None, **context: Any) -> str:
    """A page in base.html's frame: `page` marks the current nav link, `supplier` fills the header."""
    return templates.get_template(template).render(
        page=page,
        supplier=supplier and supplier.model_dump(by_alias=True, exclude_none=True),
        **context,
    )
