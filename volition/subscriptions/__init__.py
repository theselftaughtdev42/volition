"""The subscriptions module: what the business pays for on a cycle, when each renews, and what they all cost."""

from volition.core.modules import Module
from volition.subscriptions.store import MIGRATIONS
from volition.subscriptions.templates import SLUG, TEMPLATES
from volition.subscriptions.web import NAV, home_panel, router

module = Module(
    slug=SLUG,
    title="Subscriptions",
    description="What the business pays for, and when each renews.",
    router=router,
    nav=NAV,
    migrations=MIGRATIONS,
    templates=TEMPLATES,
    home_panel=home_panel,
)
