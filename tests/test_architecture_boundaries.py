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


def test_application_layer_does_not_keep_transitional_model_reexport_shim() -> None:
    models_path = PROJECT_ROOT / "app" / "application" / "models.py"
    assert not models_path.exists(), f"{models_path} should be removed after workflow import cleanup"


def test_workflow_layer_does_not_keep_months_reexport_shim() -> None:
    shim_path = PROJECT_ROOT / "app" / "application" / "workflow" / "months.py"
    assert not shim_path.exists(), f"{shim_path} should be removed after month helpers import cleanup"

    for root in [PROJECT_ROOT / "app", PROJECT_ROOT / "tests"]:
        for file_path in _iter_python_files(root):
            for imported in _iter_imports(file_path):
                assert imported != "app.application.workflow.months", (
                    f"{file_path} should import month helpers from app.application.months directly"
                )


def test_runtime_module_defers_transport_imports_to_startup_functions() -> None:
    runtime_path = PROJECT_ROOT / "app" / "bootstrap" / "runtime.py"

    for imported in _iter_imports(runtime_path):
        assert imported.split(".", maxsplit=1)[0] != "aiogram", f"{runtime_path} eagerly imports transport dependency: {imported}"
        assert not imported.startswith("app.adapters.telegram"), f"{runtime_path} eagerly imports telegram adapter: {imported}"
        assert not imported.startswith("app.adapters.web"), f"{runtime_path} eagerly imports web adapter: {imported}"


def test_package_init_modules_do_not_reexport_implementation_modules() -> None:
    package_init_files = [
        PROJECT_ROOT / "app" / "application" / "__init__.py",
        PROJECT_ROOT / "app" / "adapters" / "__init__.py",
    ]

    for file_path in package_init_files:
        assert _iter_imports(file_path) == [], f"{file_path} should stay import-light and avoid implementation re-exports"


def test_application_layer_does_not_keep_telegram_shaped_sync_wrapper() -> None:
    facade_path = PROJECT_ROOT / "app" / "application" / "facade.py"
    content = facade_path.read_text(encoding="utf-8")

    assert "SyncTelegramUserUseCase" not in content
    assert "sync_user(" not in content


def test_application_layer_does_not_keep_process_cashback_image_compatibility_wrapper() -> None:
    wrapper_path = PROJECT_ROOT / "app" / "application" / "use_cases" / "process_cashback_image.py"
    assert not wrapper_path.exists(), f"{wrapper_path} should be removed after upload use case rename cleanup"


def test_application_use_cases_do_not_hardcode_telegram_delivery_provider() -> None:
    use_cases_root = PROJECT_ROOT / "app" / "application" / "use_cases"

    for file_path in _iter_python_files(use_cases_root):
        content = file_path.read_text(encoding="utf-8")
        assert 'provider="telegram"' not in content, (
            f"{file_path} hardcodes telegram delivery/provider knowledge inside application layer"
        )


def test_domain_models_do_not_keep_user_profile_alias() -> None:
    domain_models_path = PROJECT_ROOT / "app" / "domain" / "models.py"
    content = domain_models_path.read_text(encoding="utf-8")

    assert "UserProfile =" not in content


def test_runtime_owns_reminder_loop_outside_telegram_adapter() -> None:
    runtime_path = PROJECT_ROOT / "app" / "bootstrap" / "runtime.py"
    content = runtime_path.read_text(encoding="utf-8")
    module_ast = ast.parse(content)
    telegram_adapter_source = ""
    for node in module_ast.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run_telegram_adapter":
            telegram_adapter_source = ast.get_source_segment(content, node) or ""
            break

    assert telegram_adapter_source
    assert "ReminderLoop" not in telegram_adapter_source
    assert 'name="reminder-runtime"' in content


def test_bootstrap_reminder_provider_is_config_driven() -> None:
    bootstrap_files = [
        PROJECT_ROOT / "app" / "bootstrap" / "container.py",
        PROJECT_ROOT / "app" / "bootstrap" / "runtime.py",
    ]
    for file_path in bootstrap_files:
        content = file_path.read_text(encoding="utf-8")
        assert 'delivery_provider="telegram"' not in content, (
            f"{file_path} should read reminder provider from settings instead of hardcoding telegram"
        )

    config_path = PROJECT_ROOT / "app" / "bootstrap" / "config.py"
    assert "REMINDER_DELIVERY_PROVIDER" in config_path.read_text(encoding="utf-8")
