"""The first-run setup invoicing's pages require: the supplier, then the invoice defaults."""

from typing import Annotated

from fastapi import Depends

from volition.core.web.deps import SetupIncomplete
from volition.invoicing.models import Defaults, Supplier
from volition.invoicing.store.defaults import load_defaults
from volition.invoicing.store.supplier import load_supplier


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
