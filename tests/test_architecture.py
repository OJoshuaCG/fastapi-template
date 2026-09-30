"""
Reglas de capas (ver "Arquitectura" en CLAUDE.md), verificadas leyendo los imports de app/.

    routes → controllers → services → models → core.database

Si una regla estorba en un caso real, discutirlo antes de agregar una excepción aquí.
"""

import ast
from pathlib import Path

import pytest

from app.core.environment import APP_DIR

# capa → capas del proyecto que NO puede importar
FORBIDDEN: dict[str, set[str]] = {
    "routes": {"models"},
    "controllers": {"routes"},
    "services": {"routes", "controllers"},
    "models": {"routes", "controllers", "services", "schemas"},
    "schemas": {"routes", "controllers", "services", "models"},
    "core": {"routes", "controllers", "services", "models", "schemas"},
    "utils": {"routes", "controllers", "services", "models", "schemas"},
    "exceptions": {"routes", "controllers", "services", "models", "schemas"},
    "middleware": {"routes", "controllers", "services", "models"},
}
# Librerías que cada capa no debe usar directamente
FORBIDDEN_LIBS: dict[str, set[str]] = {
    "routes": {"httpx", "sqlalchemy"},
    "controllers": {"httpx", "sqlalchemy"},
    "services": {"sqlalchemy"},
}
# Endpoints de ejemplo/diagnóstico: pueden llamar services directamente
ROUTES_MAY_USE_SERVICES = {"app/routes/v1/test.py"}


def _modules() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


def _layer(path: Path) -> str:
    return path.relative_to(APP_DIR).parts[0]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _rel(path: Path) -> str:
    return path.relative_to(APP_DIR.parent).as_posix()


@pytest.mark.parametrize("path", _modules(), ids=_rel)
def test_layer_imports(path: Path) -> None:
    layer = _layer(path)
    violations = []
    for name in _imports(path):
        parts = name.split(".")
        if parts[0] == "app" and len(parts) > 1:
            target = parts[1]
            forbidden = set(FORBIDDEN.get(layer, set()))
            if layer == "routes" and _rel(path) not in ROUTES_MAY_USE_SERVICES:
                forbidden.add("services")
            if target in forbidden:
                violations.append(f"{layer} no puede importar {target} ({name})")
        elif parts[0] in FORBIDDEN_LIBS.get(layer, set()):
            violations.append(f"{layer} no puede usar {parts[0]} directamente ({name})")
        if parts[0] == "requests":
            violations.append("`requests` bloquea el event loop: usar un ServiceClient")
    assert not violations, "\n".join(violations)


def test_async_client_only_in_service_client() -> None:
    offenders = [
        _rel(path)
        for path in _modules()
        if "AsyncClient(" in path.read_text() and _rel(path) != "app/core/http_client.py"
    ]
    assert not offenders, f"crear clientes HTTP solo vía ServiceClient: {offenders}"


def test_models_do_not_raise_http_errors() -> None:
    offenders = [
        _rel(path)
        for path in (APP_DIR / "models").rglob("*.py")
        if "AppHttpException" in path.read_text() or "HTTPException" in path.read_text()
    ]
    assert not offenders, f"los models lanzan ValueError/errores de dominio: {offenders}"
