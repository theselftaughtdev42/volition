"""The composition root: the only place that names every module."""

from volition import invoicing
from volition.core.app import create_app
from volition.upgrade import PRE_MODULE_UPGRADE

app = create_app([invoicing.module], PRE_MODULE_UPGRADE)
