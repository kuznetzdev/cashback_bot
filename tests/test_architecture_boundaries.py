from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_PREFIXES = ("aiogram", "sqlalchemy")


def _top_module(name: str) -> str:
    return name.split(".", maxsplit=1)[0]


def _iter_python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if path.is_file()]


def test_core_has_no_transport_or_orm_dependencies() -> None:
    project_root = Path(__file__).resolve().parents[1]
    core_roots = [project_root / "app" / "domain", project_root / "app" / "application"]

    for root in core_roots:
        for file_path in _iter_python_files(root):
            module_ast = ast.parse(file_path.read_text(encoding="utf-8"))
            for node in ast.walk(module_ast):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = _top_module(alias.name)
                        assert top not in FORBIDDEN_PREFIXES, f"{file_path} imports forbidden dependency: {alias.name}"
                if isinstance(node, ast.ImportFrom):
                    if node.module is None:
                        continue
                    top = _top_module(node.module)
                    assert top not in FORBIDDEN_PREFIXES, f"{file_path} imports forbidden dependency: {node.module}"
