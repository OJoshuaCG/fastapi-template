"""Contrato de app/core/environment.py (sin BD)."""

import ast
import re
from pathlib import Path

import pytest

from app.core import environment
from app.core.environment import INFRA_ONLY_VARS, ROOT_DIR, Settings

ENV_EXAMPLE = ROOT_DIR / ".env.example"
# `VAR=valor` o `# VAR=valor` (avanzadas comentadas); ignora comentarios de texto
_ENV_LINE = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)=", re.M)


def _example_keys() -> set[str]:
    return set(_ENV_LINE.findall(ENV_EXAMPLE.read_text()))


def test_env_example_and_settings_are_in_sync() -> None:
    documented = _example_keys() - INFRA_ONLY_VARS
    declared = set(Settings.model_fields)
    assert declared - documented == set(), "faltan en .env.example"
    assert documented - declared == set(), "en .env.example pero no en Settings"


def test_env_example_loads_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    # Las variables del proceso (conftest) tienen prioridad sobre el archivo: quitarlas
    for key in Settings.model_fields:
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]
    assert s.APP_ENV == "development"
    assert s.docs_enabled is True


def test_unknown_env_keys_are_reported(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=development\nDB_PASWORD=x\nWORKERS=2\n")
    assert environment.unknown_env_file_keys(env_file) == ["DB_PASWORD"]


def test_secrets_never_appear_in_repr_dump_or_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "valor-super-secreto-123"
    s = Settings(_env_file=None, APP_ENV="development", DB_PASS=secret, SECRET_KEY=secret)  # type: ignore[call-arg]
    assert secret not in repr(s) and secret not in s.model_dump_json()

    monkeypatch.setenv("DB_PORT", secret)  # inválido: no es entero
    monkeypatch.setattr(environment, "ENV_FILE", None)
    with pytest.raises(RuntimeError) as exc:
        environment._load_settings()
    assert "DB_PORT: debe ser un número entero" in str(exc.value)
    assert secret not in str(exc.value)


def test_startup_error_lists_production_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "corta")
    monkeypatch.setattr(environment, "ENV_FILE", None)
    with pytest.raises(RuntimeError, match="SECRET_KEY: debe tener al menos 32 caracteres"):
        environment._load_settings()


def _settings_attributes(tree: ast.AST) -> list[tuple[str, int, bool]]:
    """(atributo, línea, es_asignación) de cada acceso `settings.X` / `self.settings.X`."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        is_settings = (isinstance(value, ast.Name) and value.id == "settings") or (
            isinstance(value, ast.Attribute) and value.attr == "settings"
        )
        if is_settings:
            found.append((node.attr, node.lineno, isinstance(node.ctx, ast.Store)))
    return found


def test_code_only_uses_existing_settings_and_never_mutates_them() -> None:
    valid = set(Settings.model_fields) | {
        name for name in dir(Settings) if not name.startswith("_")
    }
    problems = []
    for path in [
        ROOT_DIR / "main.py",
        *(ROOT_DIR / "app").rglob("*.py"),
        *(ROOT_DIR / "tests").rglob("*.py"),
    ]:
        tree = ast.parse(path.read_text(), filename=str(path))
        for attr, line, is_store in _settings_attributes(tree):
            where = f"{path.relative_to(ROOT_DIR)}:{line} settings.{attr}"
            if attr not in valid:
                problems.append(f"{where} no existe en Settings")
            if is_store and "tests" not in path.parts:
                problems.append(f"{where}: no asignar settings en código de la app")
    assert problems == []
