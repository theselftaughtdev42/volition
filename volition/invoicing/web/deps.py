"""The first-run setup invoicing's pages require: the invoicing settings (core already requires the business)."""

from typing import Annotated

from fastapi import Depends

from volition.core.web.deps import SetupIncomplete
from volition.invoicing.models import InvoicingSettings
from volition.invoicing.store.settings import load_settings
from volition.invoicing.templates import SLUG


def require_settings() -> InvoicingSettings:
    settings = load_settings()
    if settings is None:
        raise SetupIncomplete(f"/{SLUG}/settings")
    return settings


SettingsDep = Annotated[InvoicingSettings, Depends(require_settings)]
#: For pages that don't use the settings but shouldn't be reached before they're saved.
NEEDS_SETTINGS = [Depends(require_settings)]
