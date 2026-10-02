"""Core imports no module; modules import only from core, never from each other.

Only the composition root (the files directly in `volition/`) may name every module.
"""

import ast
from pathlib import Path

import volition

PACKAGE = Path(volition.__file__).resolve().parent


def _imported(tree: ast.Module, package: list[str]) -> set[str]:
    """Every absolute module name `tree` imports; `package` is its own package, for relative imports."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            source = ".".join([*base, *([node.module] if node.module else [])])
            # `from volition import invoicing` imports the volition.invoicing package.
            names.update(f"{source}.{alias.name}" for alias in node.names)
    return names


def violations(root: Path) -> list[str]:
    """`root` is the `volition` package directory."""
    found = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root.parent).with_suffix("").parts
        if len(parts) == 2:
            continue  # the composition root
        owner = parts[1]
        for name in sorted(_imported(ast.parse(path.read_text(), str(path)), list(parts[:-1]))):
            target = name.split(".")
            if target[0] != "volition" or len(target) < 2:
                continue
            if target[1] not in ("core", owner):
                found.append(f"{'/'.join(parts)}.py imports {name}")
    return found


def test_core_imports_no_module_and_modules_only_import_core() -> None:
    assert violations(PACKAGE) == []


def test_the_check_catches_crossed_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "volition"
    files = {
        "app.py": "from volition import invoicing, savings",
        "core/app.py": "from volition.core.config import ROOT\nfrom volition.invoicing.models import Invoice",
        "core/templates.py": "from volition import invoicing",
        "core/web.py": "from volition.app import app",
        "invoicing/models.py": (
            "from volition.core.errors import validate\nfrom ..savings import pots\nimport volition.savings"
        ),
        "invoicing/web/pages.py": "from ..models import Invoice\nfrom ...core.modules import NavLink",
        "savings/__init__.py": "from volition.savings.pots import Pot",
    }
    for name, source in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(source)
    assert violations(root) == [
        "volition/core/app.py imports volition.invoicing.models.Invoice",
        "volition/core/templates.py imports volition.invoicing",
        "volition/core/web.py imports volition.app.app",
        "volition/invoicing/models.py imports volition.savings",
        "volition/invoicing/models.py imports volition.savings.pots",
    ]
