from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_TOP_LEVEL = {"aiogram", "fastapi", "sqlalchemy"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _iter_python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if path.is_file()]


def _iter_imports(file_path: Path) -> list[str]:
    module_ast = ast.parse(file_path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(module_ast):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return imports


def test_domain_and_application_do_not_import_adapters_or_frameworks() -> None:
    protected_roots = [PROJECT_ROOT / "app" / "domain", PROJECT_ROOT / "app" / "application"]

    for root in protected_roots:
        for file_path in _iter_python_files(root):
            for imported in _iter_imports(file_path):
                top_level = imported.split(".", maxsplit=1)[0]
                assert top_level not in FORBIDDEN_TOP_LEVEL, f"{file_path} imports forbidden dependency: {imported}"
                assert not imported.startswith("app.adapters"), f"{file_path} imports adapter dependency: {imported}"


def test_web_adapter_does_not_import_telegram_adapter_modules() -> None:
    web_root = PROJECT_ROOT / "app" / "adapters" / "web"

    for file_path in _iter_python_files(web_root):
        for imported in _iter_imports(file_path):
            assert not imported.startswith("app.adapters.telegram"), (
                f"{file_path} imports telegram adapter dependency: {imported}"
            )


def test_shared_i18n_module_is_not_hidden_under_telegram_adapter() -> None:
    localizer_path = PROJECT_ROOT / "app" / "i18n" / "localizer.py"
    assert localizer_path.exists(), f"Expected shared localizer at {localizer_path}"


def test_workflow_and_presenters_do_not_pull_persistence_concerns() -> None:
    protected_roots = [
        PROJECT_ROOT / "app" / "application" / "workflow",
        PROJECT_ROOT / "app" / "application" / "presenters",
    ]

    forbidden_tokens = ("UnitOfWorkPort", "uow_factory", "AsyncSession")

    for root in protected_roots:
        for file_path in _iter_python_files(root):
            content = file_path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                assert token not in content, f"{file_path} leaks persistence concern: {token}"


def test_application_models_marks_workflow_reexports_as_transitional() -> None:
    models_path = PROJECT_ROOT / "app" / "application" / "models.py"
    content = models_path.read_text(encoding="utf-8")

    assert "Transitional compatibility re-exports" in content
