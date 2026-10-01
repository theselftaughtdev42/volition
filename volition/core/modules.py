"""The module contract: what a module gives the shell to be part of the app."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter


@dataclass(frozen=True)
class NavLink:
    title: str
    #: Relative to the module's URL prefix.
    path: str


@dataclass(frozen=True)
class Module:
    #: e.g. "invoicing": the module's URL prefix, template namespace, migration namespace and table prefix
    #: ("invoicing_clients"). Never "core", which versions the shell's own tables.
    slug: str
    title: str
    #: One line saying what the module does.
    description: str
    router: APIRouter
    #: The module's own pages, in nav order.
    nav: tuple[NavLink, ...]
    #: SQL scripts, one per schema version, applied after core's and earlier modules'. Append new steps, never edit
    #: applied ones.
    migrations: tuple[str, ...]
    #: The module's template directory, loaded as "<slug>/...".
    templates: Path
