"""The composition root: the only place that names every module."""

from volition import invoicing
from volition.core.app import create_app

app = create_app([invoicing.module])
