"""Dependencies any module's pages can use: the first-run redirect, and the submitted form."""

from typing import Annotated

from fastapi import Depends, Request
from starlette.datastructures import FormData


class SetupIncomplete(Exception):
    """Something the first run asks for hasn't been saved yet; `path` is the page that asks for it.

    Raise it from a dependency: the app redirects there.
    """

    def __init__(self, path: str) -> None:
        self.path = path


async def form_data(request: Request) -> FormData:
    return await request.form()


FormDep = Annotated[FormData, Depends(form_data)]
