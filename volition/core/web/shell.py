"""The frame base.html puts around every page: the modules nav, the current module's own nav, and what is current."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from volition.core.modules import Module


@dataclass(frozen=True)
class NavItem:
    title: str
    href: str
    current: bool


@dataclass(frozen=True)
class Shell:
    #: Every module, the current one marked.
    modules: tuple[NavItem, ...]
    #: The page's module, or None outside any module (e.g. on the home page).
    module: Module | None
    #: The current module's own pages, the current one marked; empty outside a module.
    pages: tuple[NavItem, ...]


def module_href(module: Module) -> str:
    return f"/{module.slug}/"


def shell_for(modules: Sequence[Module], path: str) -> Shell:
    """The shell around the page at `path`, e.g. "/invoicing/clients/new" marks Invoicing and its Clients link."""
    current = next((m for m in modules if _within(path, f"/{m.slug}")), None)
    pages: tuple[NavItem, ...] = ()
    if current is not None:
        prefix = f"/{current.slug}"
        page = path.removeprefix(prefix) or "/"
        # The most specific link the page sits under, so "/" (the module's home) only when nothing else is.
        marked = max((link for link in current.nav if _within(page, link.path)), key=lambda link: len(link.path), default=None)
        pages = tuple(NavItem(link.title, prefix + link.path, link is marked) for link in current.nav)
    return Shell(
        modules=tuple(NavItem(m.title, module_href(m), m is current) for m in modules),
        module=current,
        pages=pages,
    )


def _within(path: str, base: str) -> bool:
    """Whether `path` is `base` or under it, segment by segment ("/clients/1" is under "/clients", not "/client")."""
    base = base.rstrip("/")
    return path == base or path.startswith(base + "/")


def shell(request: Request) -> Shell:
    return shell_for(request.app.state.modules, request.url.path)


ShellDep = Annotated[Shell, Depends(shell)]
