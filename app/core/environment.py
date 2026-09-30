"""
Variables de entorno del proyecto: tipadas y validadas al arrancar (pydantic-settings).

Uso:
    from app.core.environment import settings

    settings.DB_HOST                     # MAYÚSCULA = variable de entorno (mismo nombre en .env)
    settings.DB_PASS.get_secret_value()  # secretos (SecretStr): SECRET_KEY, DB_PASS,
                                         # DOCS_PASSWORD, RATE_LIMIT_REDIS_URL (repr: '**********')
    settings.is_production               # minúscula = valor derivado (property)

Reglas:
- Leer `settings.X` dentro de la función, no copiarlo a constantes de módulo (los tests no
  podrían cambiarlo). Excepción: valores del esquema OpenAPI (marcados "leído al importar").
- Si falta o es inválida una variable la app NO arranca y lista las variables con error por nombre.
- Variable vacía en el .env (`DOCS_ENABLED=`) = usar el default.

Agregar una variable (2 pasos; tests/test_environment.py falla si falta uno):
    1. Campo aquí, en su sección, con tipo y default seguro (sin default = obligatoria).
    2. La misma variable en .env.example, en la misma sección, con un comentario de una línea.

En tests:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)   # se revierte solo
"""

import os
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.utils.validation_messages import error_message

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"

# ENV_FILE elige el archivo a leer; vacío = no leer ninguno (tests, contenedores)
ENV_FILE: str | None = os.getenv("ENV_FILE", str(ROOT_DIR / ".env")) or None

# Variables del .env que usa la infraestructura (docker-compose / entrypoint), no la app
INFRA_ONLY_VARS = frozenset({"WORKERS", "ENV_FILE"})

PAGINATION_HARD_CAP = 200
_WEAK_SECRETS = {"", "changeme", "super_secret_key", "secret", "password", "admin"}
DEFAULT_ENCODING_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def parse_encryption_keys(raw: str) -> list[bytes]:
    """Llaves Fernet de ENCRYPTION_KEYS (coma). Lanza ValueError si alguna es inválida."""
    keys = [k.strip().encode() for k in raw.split(",") if k.strip()]
    for position, key in enumerate(keys, start=1):
        try:
            Fernet(key)
        except (ValueError, TypeError):
            raise ValueError(f"la llave #{position} no es una llave Fernet válida") from None
    return keys


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # "VAR=" en el .env = usar el default
        hide_input_in_errors=True,  # los errores de validación nunca muestran valores (secretos)
        extra="ignore",  # el .env también trae variables de infraestructura (INFRA_ONLY_VARS)
    )

    # ======= Application ======= #
    # Obligatorio: sin default para que nadie arranque "production" o "development" por accidente
    APP_ENV: Literal["development", "test", "staging", "production"]
    APP_NAME: str = "FastAPI Project"
    # Reservado para la autenticación del proyecto (en producción: mínimo 32 caracteres)
    SECRET_KEY: SecretStr = SecretStr("")

    # ======= Logger ======= #
    LOGGER_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: Literal["text", "json"] = "text"
    LOGGER_MIDDLEWARE_ENABLED: bool = True
    LOGGER_MIDDLEWARE_SHOW_HEADERS: bool = False
    LOGGER_MIDDLEWARE_SHOW_QUERY_PARAMS: bool = True
    LOGGER_MIDDLEWARE_SHOW_PATH_PARAMS: bool = True
    LOGGER_MIDDLEWARE_ERRORS_ONLY: bool = False
    # Loguea también las AppHttpException 4xx (las 5xx y no controladas se loguean siempre)
    LOGGER_EXCEPTIONS_ENABLED: bool = False

    # ======= Docs ======= #
    # Sin definir = habilitado fuera de producción, deshabilitado en producción (ver docs_enabled)
    DOCS_ENABLED: bool | None = None
    DOCS_PASSWORD_ENABLED: bool = False
    DOCS_USER: str = "admin"
    DOCS_PASSWORD: SecretStr = SecretStr("")

    # ======= Rate limiting ======= #
    # Límite por ruta (rate_limit()). El límite global por IP lo aplica nginx (limit_req).
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REDIS_ENABLED: bool = False
    RATE_LIMIT_REDIS_URL: SecretStr = SecretStr("redis://localhost:6379")

    # ======= Pagination / Request / Uploads ======= #
    PAGINATION_MAX_SIZE: int = Field(50, ge=1)
    REQUEST_MAX_SIZE_MB: float = Field(10, gt=0)
    UPLOAD_DIR: Path = Path("uploads")

    # ======= CORS ======= #
    # Orígenes separados por coma. Vacío = CORS deshabilitado
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []
    # Se ignora (False) si CORS_ORIGINS contiene "*" (ver cors_allow_credentials)
    CORS_ALLOW_CREDENTIALS: bool = True

    # ======= Database (MariaDB / MySQL) ======= #
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = ""
    DB_PASS: SecretStr = SecretStr("")
    DB_NAME: str = ""
    # Collation de la sesión (SET NAMES por conexión). Debe coincidir con la de la base/tablas:
    # si difieren, MariaDB puede fallar con "Illegal mix of collations" (variables o parámetros
    # en SPs, CONCAT con literales, tablas temporales que heredan la de la sesión)
    DB_COLLATION: str = "utf8mb4_unicode_ci"
    DB_POOL_SIZE: int = Field(10, ge=1)
    DB_MAX_OVERFLOW: int = Field(10, ge=0)
    # Espera máxima por una conexión libre del pool. Bajo a propósito: con el pool lleno
    # esperar no ayuda; fallar rápido con 503 evita congelar el worker (default SQLAlchemy = 30s)
    DB_POOL_TIMEOUT: float = Field(3, gt=0)
    # Debe ser menor que wait_timeout del servidor para no reutilizar conexiones muertas
    DB_POOL_RECYCLE: int = Field(180, gt=0)
    DB_CONNECT_TIMEOUT: int = Field(5, gt=0)
    # Tiempo máximo por sentencia en el servidor (segundos). 0 = sin límite
    DB_STATEMENT_TIMEOUT: float = Field(30, ge=0)

    # ======= Security ======= #
    # Llaves Fernet separadas por coma: la primera cifra, todas descifran (rotación).
    # Cifran contraseñas y datos sensibles reversibles. Nunca reutilizar SECRET_KEY.
    ENCRYPTION_KEYS: SecretStr = SecretStr("")
    # Alfabeto de sqids para ofuscar IDs (propio del proyecto; en producción no el default)
    ENCODING_ALPHABET: str = DEFAULT_ENCODING_ALPHABET
    ENCODING_MIN_LENGTH: int = Field(8, ge=0, le=255)

    # ======= HTTP client (servicios externos) ======= #
    # Timeout total por request (cada servicio puede definir el suyo)
    HTTP_CLIENT_TIMEOUT: float = Field(10, gt=0)
    HTTP_CLIENT_CONNECT_TIMEOUT: float = Field(5, gt=0)
    # Espera máxima por una conexión libre del pool del servicio (fallar rápido con 503)
    HTTP_CLIENT_POOL_TIMEOUT: float = Field(2, gt=0)
    # Conexiones máximas por servicio externo (cada servicio tiene su propio pool)
    HTTP_CLIENT_MAX_CONNECTIONS: int = Field(20, ge=1)
    # Reintentos en métodos idempotentes (GET/HEAD/OPTIONS/PUT/DELETE) ante fallos transitorios
    HTTP_CLIENT_MAX_RETRIES: int = Field(2, ge=0, le=5)

    # ======= Observabilidad ======= #
    # Telemetría nativa de FastAPI (OpenTelemetry). Sin OTEL_EXPORTER_OTLP_ENDPOINT no exporta nada
    OTEL_ENABLED: bool = True

    # ------------------------------------------------------------------ #
    # Validación (solo valida: no modifica campos)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("PAGINATION_MAX_SIZE")
    @classmethod
    def _cap_pagination(cls, value: int) -> int:
        return min(value, PAGINATION_HARD_CAP)

    @field_validator("UPLOAD_DIR")
    @classmethod
    def _absolute_upload_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (ROOT_DIR / value).resolve()

    @field_validator("ENCODING_ALPHABET")
    @classmethod
    def _valid_alphabet(cls, value: str) -> str:
        if len(value) < 5 or len(set(value)) != len(value) or not value.isascii():
            raise ValueError("debe tener al menos 5 caracteres ASCII únicos")
        return value

    @model_validator(mode="after")
    def _production_rules(self) -> Self:
        errors: list[str] = []
        raw_keys = self.ENCRYPTION_KEYS.get_secret_value()
        if raw_keys:
            try:
                parse_encryption_keys(raw_keys)
            except ValueError as exc:
                errors.append(f"ENCRYPTION_KEYS: {exc}")
        if self.is_deployed and not raw_keys:
            errors.append(f"ENCRYPTION_KEYS: obligatorio en {self.APP_ENV}")
        if self.is_production and self.ENCODING_ALPHABET == DEFAULT_ENCODING_ALPHABET:
            errors.append("ENCODING_ALPHABET: usar un alfabeto propio (barajado) en producción")
        if self.is_production:
            # Un secreto por propósito: si uno se filtra o rota, no arrastra a los demás
            used = [
                s
                for s in (
                    self.SECRET_KEY.get_secret_value(),
                    self.DB_PASS.get_secret_value(),
                    raw_keys,
                )
                if s
            ]
            if len(set(used)) != len(used):
                errors.append("SECRET_KEY / DB_PASS / ENCRYPTION_KEYS: deben ser distintos")
            if len(self.SECRET_KEY.get_secret_value()) < 32:
                errors.append("SECRET_KEY: debe tener al menos 32 caracteres en producción")
            if self.DB_PASS.get_secret_value() in _WEAK_SECRETS:
                errors.append("DB_PASS: vacío o débil en producción")
            if "*" in self.CORS_ORIGINS:
                errors.append("CORS_ORIGINS: '*' no está permitido en producción")
        # Docs protegidos con contraseña débil: error en cualquier entorno desplegado
        if self.is_deployed and self.docs_enabled and self.DOCS_PASSWORD_ENABLED:
            docs_pass = self.DOCS_PASSWORD.get_secret_value()
            if len(docs_pass) < 12 or docs_pass in _WEAK_SECRETS:
                errors.append(f"DOCS_PASSWORD: debe tener al menos 12 caracteres en {self.APP_ENV}")
        if errors:
            raise ValueError("\n  - ".join(errors))
        return self

    # ------------------------------------------------------------------ #
    # Valores derivados (minúscula): se calculan siempre, nunca quedan desactualizados

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_deployed(self) -> bool:
        """staging y production: entornos accesibles por terceros."""
        return self.APP_ENV in ("staging", "production")

    @property
    def docs_enabled(self) -> bool:
        return self.DOCS_ENABLED if self.DOCS_ENABLED is not None else not self.is_production

    @property
    def cors_allow_credentials(self) -> bool:
        # Con "*" + credenciales Starlette refleja cualquier Origin: acceso abierto con cookies
        return self.CORS_ALLOW_CREDENTIALS and "*" not in self.CORS_ORIGINS

    @property
    def request_max_bytes(self) -> int:
        return int(self.REQUEST_MAX_SIZE_MB * 1024 * 1024)

    @property
    def startup_warnings(self) -> list[str]:
        """Advertencias no fatales de configuración (se loguean en el lifespan)."""
        warnings: list[str] = []
        if not self.SECRET_KEY.get_secret_value():
            warnings.append("SECRET_KEY no está definido (reservado para la auth del proyecto)")
        if self.is_production and self.docs_enabled and not self.DOCS_PASSWORD_ENABLED:
            warnings.append("Documentación pública habilitada en producción")
        if not self.ENCRYPTION_KEYS.get_secret_value():
            warnings.append(
                "ENCRYPTION_KEYS no está definido: se usa una llave temporal (lo cifrado no se "
                'podrá leer al reiniciar). Generar con: uv run python -c "from '
                'cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        unknown = unknown_env_file_keys()
        if unknown:
            warnings.append(f"Variables desconocidas en {ENV_FILE} (¿typo?): {', '.join(unknown)}")
        return warnings


def unknown_env_file_keys(env_file: str | Path | None = None) -> list[str]:
    """Claves del .env que no son campos de Settings ni de infraestructura (ej. DB_PASWORD)."""
    path = Path(env_file) if env_file else (Path(ENV_FILE) if ENV_FILE else None)
    if path is None or not path.is_file():
        return []
    known = {name.upper() for name in Settings.model_fields} | INFRA_ONLY_VARS
    return sorted(key for key in dotenv_values(path) if key.upper() not in known)


def _load_settings() -> Settings:
    """Carga la configuración; si es inválida, un error legible por variable y sin valores."""
    try:
        return Settings(_env_file=ENV_FILE)  # type: ignore[call-arg]  # APP_ENV viene del entorno
    except ValidationError as exc:
        problems: list[str] = []
        for err in exc.errors(include_input=False):
            if err["loc"]:
                variable = str(err["loc"][0]).upper()
                problems.append(f"{variable}: {error_message(dict(err))}")
            else:  # reglas del model_validator (ya incluyen el nombre de la variable)
                problems.append(str(err.get("msg", "")).removeprefix("Value error, "))
        origin = ENV_FILE or "variables de entorno"
        raise RuntimeError(
            f"Configuración inválida ({origin}):\n  - " + "\n  - ".join(problems)
        ) from None


settings = _load_settings()
