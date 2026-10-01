"""Dependencies the pages share: the first-run setup they require, and the submitted form."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.datastructures import FormData

from volition.models import Defaults, Supplier
from volition.store.defaults import load_defaults
from volition.store.supplier import load_supplier


class SetupIncomplete(Exception):
    """Something the first run asks for hasn't been saved yet; `path` is the page that asks for it."""

    def __init__(self, path: str) -> None:
        self.path = path


def require_supplier() -> Supplier:
    supplier = load_supplier()
    if supplier is None:
        raise SetupIncomplete("/supplier")
    return supplier


SupplierDep = Annotated[Supplier, Depends(require_supplier)]


def require_defaults(_: SupplierDep) -> Defaults:
    """Also requires the supplier, so the first run asks for that first."""
    defaults = load_defaults()
    if defaults is None:
        raise SetupIncomplete("/defaults")
    return defaults


DefaultsDep = Annotated[Defaults, Depends(require_defaults)]
#: For pages that don't use the defaults but shouldn't be reached before they're set.
NEEDS_DEFAULTS = [Depends(require_defaults)]


async def form_data(request: Request) -> FormData:
    return await request.form()


FormDep = Annotated[FormData, Depends(form_data)]
