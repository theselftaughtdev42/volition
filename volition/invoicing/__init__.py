"""The invoicing module: clients, the invoicing settings and the numbered PDF invoices made from them."""

from fastapi import APIRouter

from volition.core.modules import Module
from volition.invoicing.store.schema import MIGRATIONS
from volition.invoicing.templates import SLUG, TEMPLATES
from volition.invoicing.web.deps import NEEDS_SETTINGS
from volition.invoicing.web.pages import NAV, clients, invoice, settings

router = APIRouter()
for page in (invoice, clients):
    # Invoicing's first run asks for the settings before anything else.
    router.include_router(page.router, dependencies=NEEDS_SETTINGS)
router.include_router(settings.router)

module = Module(
    slug=SLUG,
    title="Invoicing",
    description="Branded PDF invoices for clients, numbered in sequence.",
    router=router,
    nav=NAV,
    migrations=MIGRATIONS,
    templates=TEMPLATES,
)
