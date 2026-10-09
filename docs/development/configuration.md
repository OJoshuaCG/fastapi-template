# Configuración y variables de entorno

Cómo se lee, valida y extiende la configuración (`app/core/environment.py`). Léelo antes de agregar o usar una variable de entorno.

## Configuración (`app/core/environment.py`)

```python
from app.core.environment import settings

settings.DB_HOST                      # MAYÚSCULA = variable de entorno (mismo nombre que en .env)
settings.DB_PASS.get_secret_value()   # secretos (SecretStr): SECRET_KEY, DB_PASS, ENCRYPTION_KEYS, DOCS_PASSWORD...
settings.is_production                # minúscula = valor derivado (property)
```

- Una sola forma de acceso: el singleton `settings` del módulo (no hay `get_settings()` ni `SettingsDep`).
  `create_app()`, `create_versioned_app()` y `build_v1_router()` no reciben `settings`: lo importan.
- Campos en MAYÚSCULA idénticos a la variable de entorno. Derivados en minúscula (properties, siempre
  calculados): `is_production`, `is_development`, `is_deployed`, `docs_enabled`, `cors_allow_credentials`,
  `request_max_bytes`, `startup_warnings`.
- Leer `settings.X` **dentro de la función**, no copiarlo a constantes de módulo (los tests no podrían
  cambiarlo). Excepción: valores que forman parte del esquema OpenAPI, marcados `# leído al importar`
  (`PAGINATION_MAX_SIZE` en `app/utils/list_query.py`, `RATE_LIMIT_LOGIN` en `app/routes/v1/test.py`).
- `APP_ENV` es obligatorio (`development | test | staging | production`).
- Variable vacía en el `.env` (`DOCS_ENABLED=`) = usar el default (`env_ignore_empty=True`).
- Configuración inválida → la app no arranca: `RuntimeError` que lista las variables con error **por nombre**,
  en español, sin mostrar nunca los valores (`hide_input_in_errors=True`).
- En producción falla al arrancar con: `SECRET_KEY` < 32 caracteres, `DB_PASS` débil, `CORS_ORIGINS=*`,
  `ENCODING_ALPHABET` por defecto, o secretos repetidos (`SECRET_KEY`/`DB_PASS`/`ENCRYPTION_KEYS`).
  En staging y producción (`is_deployed`) también sin `ENCRYPTION_KEYS` o con `DOCS_PASSWORD` débil si los
  docs están protegidos. `ENCRYPTION_KEYS` inválida falla en cualquier entorno. Docs deshabilitados por
  defecto en producción.
- **Un secreto por propósito**: `SECRET_KEY` (auth del proyecto), `ENCRYPTION_KEYS` (cifrado), `ENCODING_ALPHABET`
  (IDs públicos), `DB_PASS`. Nunca derivar uno de otro ni reutilizar `SECRET_KEY` para cifrar.
- Integraciones externas: solo credenciales al env, con prefijo por servicio (`<NAME>_TOKEN`, `SecretStr`).
  La URL base va fija en el service; `<NAME>_BASE_URL` solo si cambia entre entornos (sandbox/producción).
- `SECRET_KEY` queda reservado para la auth del proyecto (el template aún no lo usa), pero se valida en producción.
- `ENV_FILE` elige el archivo `.env` a leer (vacío = ninguno; los tests lo dejan vacío para que el `.env`
  del desarrollador no les afecte). `extra="ignore"`: el `.env` también trae variables de infraestructura
  (`INFRA_ONLY_VARS` = `WORKERS`, `ENV_FILE`). `startup_warnings` (se loguea al arrancar)
  avisa además de claves desconocidas en el `.env` (typos como `DB_PASWORD`).
- `.env.example`: sin comentar = **revisar en cada proyecto/entorno** (cambian entre dev/staging/prod o deben coincidir con nginx/BD/workers); comentadas = **opcionales** con default seguro (`# VAR=default`).

**Agregar una variable** (2 pasos; `tests/test_environment.py` falla si falta uno):

1. Campo en `Settings`, en su sección, con tipo y default seguro (sin default = obligatoria).
2. La misma variable en `.env.example`, en la misma sección, con un comentario de una línea.

`tests/test_environment.py` verifica que `Settings` y `.env.example` estén sincronizados, que `.env.example`
cargue tal cual, que los secretos no se filtren (repr, dump, errores) y, por AST, que todo `settings.X` usado
exista y que el código de la app nunca asigne `settings`.

En tests:

```python
monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)   # se revierte solo
Settings(_env_file=None, APP_ENV="production", ...)          # tests de validación (tests/test_settings.py)
```

Nunca `cache_clear()` ni reasignar el módulo o el singleton.

