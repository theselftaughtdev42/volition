"""The invoicing module: clients, the supplier, invoice defaults and the numbered PDF invoices made from them."""

from fastapi import APIRouter

from volition.core.modules import Module
from volition.invoicing.store.schema import MIGRATIONS
from volition.invoicing.templates import SLUG, TEMPLATES
from volition.invoicing.web.pages import NAV, clients, defaults, invoice, supplier

router = APIRouter()
for page in (invoice, clients, defaults, supplier):
    router.include_router(page.router)

module = Module(
    slug=SLUG,
    title="Invoicing",
    description="Branded PDF invoices for clients, numbered in sequence.",
    router=router,
    nav=NAV,
    migrations=MIGRATIONS,
    templates=TEMPLATES,
)
