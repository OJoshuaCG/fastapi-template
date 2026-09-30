"""Validación de configuración (sin BD). Nunca modifica el singleton `settings`."""

import pytest
from pydantic import ValidationError

from app.core.environment import DEFAULT_ENCODING_ALPHABET, Settings

STRONG = "x" * 40
KEY = "S9DVkkctIR1n6QrUrNU5QdV6h8wrJdR-j2Yw6gz8DqE="
ALPHABET = "k3G7QAe51FCsPW92uEOyq4Bg6Sp8YzVTmnU0liwDdHXLajZrfxNhobJIRcMvKt"
PROD = {"APP_ENV": "production", "SECRET_KEY": STRONG, "DB_PASS": "y" * 40}
PROD_SECURE = {**PROD, "ENCRYPTION_KEYS": KEY, "ENCODING_ALPHABET": ALPHABET}


def make(**env: object) -> Settings:
    # Un kwarg que no es campo se descartaría en silencio (extra="ignore"): fallar aquí
    unknown = set(env) - set(Settings.model_fields)
    assert not unknown, f"no son campos de Settings: {unknown}"
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_app_env_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError, match="APP_ENV"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_cors_csv_is_split() -> None:
    s = make(APP_ENV="development", CORS_ORIGINS="https://a.com, https://b.com ,")
    assert s.CORS_ORIGINS == ["https://a.com", "https://b.com"]


def test_cors_wildcard_disables_credentials() -> None:
    s = make(APP_ENV="development", CORS_ORIGINS="*")
    assert s.cors_allow_credentials is False


def test_production_fails_fast_on_weak_config() -> None:
    with pytest.raises(ValidationError) as exc:
        make(APP_ENV="production", SECRET_KEY="short", DB_PASS="password", CORS_ORIGINS="*")
    message = str(exc.value)
    assert "SECRET_KEY" in message and "DB_PASS" in message and "CORS_ORIGINS" in message


def test_production_defaults_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    s = make(**PROD_SECURE)
    assert s.docs_enabled is False
    assert s.CORS_ORIGINS == []


def test_docs_enabled_derived_from_app_env() -> None:
    assert make(APP_ENV="development").docs_enabled is True
    assert make(APP_ENV="development", DOCS_ENABLED=False).docs_enabled is False


def test_pagination_hard_cap() -> None:
    assert make(APP_ENV="development", PAGINATION_MAX_SIZE=999).PAGINATION_MAX_SIZE == 200


def test_weak_docs_password_rejected_in_staging() -> None:
    with pytest.raises(ValidationError, match="DOCS_PASSWORD"):
        make(APP_ENV="staging", DOCS_ENABLED=True, DOCS_PASSWORD_ENABLED=True, DOCS_PASSWORD="")


def test_startup_warnings_are_computed_not_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STARTUP_WARNINGS", '["inyectado"]')
    s = make(APP_ENV="development", SECRET_KEY="")
    assert "inyectado" not in s.startup_warnings
    assert any("SECRET_KEY" in w for w in s.startup_warnings)


def test_encryption_keys_required_when_deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_KEYS")  # la define conftest
    for app_env in ("staging", "production"):
        with pytest.raises(ValidationError, match="ENCRYPTION_KEYS: obligatorio"):
            make(**{**PROD_SECURE, "APP_ENV": app_env, "ENCRYPTION_KEYS": ""})
    s = make(APP_ENV="development")  # en desarrollo: llave temporal + aviso
    assert any("ENCRYPTION_KEYS" in w for w in s.startup_warnings)


def test_invalid_encryption_key_rejected_in_any_env() -> None:
    with pytest.raises(ValidationError, match="la llave #2 no es una llave Fernet"):
        make(APP_ENV="development", ENCRYPTION_KEYS=f"{KEY}, no-es-una-llave")


def test_production_requires_own_ids_alphabet() -> None:
    with pytest.raises(ValidationError, match="ENCODING_ALPHABET"):
        make(**{**PROD_SECURE, "ENCODING_ALPHABET": DEFAULT_ENCODING_ALPHABET})
    with pytest.raises(ValidationError, match="ENCODING_ALPHABET"):
        make(APP_ENV="development", ENCODING_ALPHABET="aabbc")  # caracteres repetidos


def test_production_secrets_must_be_distinct() -> None:
    with pytest.raises(ValidationError, match="deben ser distintos"):
        make(**{**PROD_SECURE, "DB_PASS": STRONG})
