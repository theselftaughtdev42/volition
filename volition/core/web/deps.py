"""Dependencies any module's pages can use: the first-run redirect, the business, and the submitted form."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.datastructures import FormData

from volition.core.models import Business
from volition.core.store.business import load_business


class SetupIncomplete(Exception):
    """Something the first run asks for hasn't been saved yet; `path` is the page that asks for it.

    Raise it from a dependency: the app redirects there.
    """

    def __init__(self, path: str) -> None:
        self.path = path


#: Where the business is entered, and where every other page redirects until it has been.
BUSINESS_PATH = "/business"


def saved_business() -> Business | None:
    """None on the first run. A dependency, so it is loaded once per request however many others use it."""
    return load_business()


def require_business(business: Annotated[Business | None, Depends(saved_business)]) -> Business:
    if business is None:
        raise SetupIncomplete(BUSINESS_PATH)
    return business


BusinessDep = Annotated[Business, Depends(require_business)]


async def form_data(request: Request) -> FormData:
    return await request.form()


FormDep = Annotated[FormData, Depends(form_data)]
