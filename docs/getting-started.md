# Guía de Inicio Rápido

Levantar el proyecto en local, de cero a la primera request.

## Requisitos Previos

- **Python 3.13+** (`.python-version` fija 3.14; uv lo descarga si no está)
- **[uv](https://docs.astral.sh/uv/)**
- **MariaDB 10.6+/11 o MySQL 8** — local o con Docker
- Git

## Paso 1: Instalar uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

uv --version
```

## Paso 2: Clonar el Proyecto

```bash
git clone <tu-repositorio> mi-proyecto
cd mi-proyecto

# Si inicias un proyecto nuevo desde esta plantilla:
rm -rf .git && git init
```

## Paso 3: Instalar Dependencias

```bash
uv sync                  # dependencias + grupo dev (pytest, ruff, detect-secrets...)
uv sync --extra redis    # opcional: rate limit compartido en Redis
```

## Paso 4: Configurar Variables de Entorno

```bash
cp .env.example .env
```

`APP_ENV` es **obligatorio**: sin `.env` (o sin la variable en el entorno) la app no arranca. `.env.example` es la referencia completa y comentada; para desarrollo basta con ajustar:

```env
APP_ENV=development
DB_HOST=localhost
DB_PORT=3306
DB_USER=app
DB_PASS=app_pass
DB_NAME=app
CORS_ORIGINS=http://localhost:3000
```

Notas:
- Los comentarios van en su propia línea, no al final del valor.
- En `.env.example` van sin comentar las variables que se revisan en cada proyecto y entorno; las opcionales están comentadas con su default seguro (`# VAR=default`): descomentar solo para cambiarlas.
- Una variable vacía (`VAR=`) usa el default. Ej.: `DOCS_ENABLED` vacío o sin definir = docs habilitadas fuera de producción.
- `SECRET_KEY` está reservado para la auth del proyecto (el template aún no lo usa). Vacío solo genera un warning fuera de producción; en producción debe tener 32+ caracteres.
- `ENV_FILE` (variable de entorno del proceso) permite leer otro archivo en vez de `.env`; vacío = no leer ninguno.

## Paso 5: Base de Datos

La app usa **solo MariaDB / MySQL** (driver async `asyncmy`).

### Opción A — MariaDB con Docker

```bash
docker run -d --name mariadb-dev -p 3306:3306 \
  -e MARIADB_RANDOM_ROOT_PASSWORD=1 \
  -e MARIADB_DATABASE=app \
  -e MARIADB_USER=app \
  -e MARIADB_PASSWORD=app_pass \
  mariadb:11 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

La collation del servidor debe coincidir con `DB_COLLATION` (ver [Collation](features/database.md#collation-db_collation)).

### Opción B — Servidor existente

Crear la base con la misma collation que `DB_COLLATION`:

```sql
CREATE DATABASE app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'app'@'%' IDENTIFIED BY 'app_pass';
GRANT ALL PRIVILEGES ON app.* TO 'app'@'%';
FLUSH PRIVILEGES;
```

### Crear el esquema

El esquema está en SQL plano en `database/init/` (no se usa Alembic). La base arranca vacía (también con `docker compose up`): aplicar los scripts en orden con el gestor de BD (DBeaver, HeidiSQL, DataGrip...) o con el cliente `mariadb`:

```bash
mariadb -h localhost -u app -p app < database/init/001_users.sql    # crea la tabla users
mariadb -h localhost -u app -p app < database/procedures/sp_user_stats.sql   # SP de ejemplo
```

Los procedures usan `DELIMITER`: aplicarlos con el cliente `mariadb` o un gestor que lo soporte. Ver [database/README.md](../database/README.md).

## Paso 6: Ejecutar

```bash
uv run fastapi dev                                  # desarrollo con reload
uv run fastapi dev --host 0.0.0.0 --port 8080       # host/puerto específicos
uv run fastapi run                                  # modo producción local
```

En producción se usa `uvicorn main:app --workers N` a través de `docker/scripts/entrypoint.sh` (ver [deployment.md](deployment.md)).

Si la BD no está disponible al arrancar, la app **igual inicia** (se registra un warning) y `/ready` responde 503 hasta que la BD vuelva.

## Paso 7: Verificar

| URL | Resultado esperado |
|---|---|
| `GET /health` | `{"status": "ok", "service": "..."}` |
| `GET /ready` | `{"status": "ok", "checks": {"database": "up"}}` (503 si la BD no responde) |
| `/api/v1/docs` | Swagger UI |
| `GET /api/v1/test/ping` | `{"data": {"message": "pong!"}}` |
| `POST /api/v1/users` | Crea un usuario de ejemplo |

```bash
curl -s http://localhost:8000/ready
curl -s -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "email": "john@example.com", "password": "supersecret"}'
```

Toda respuesta incluye el header `X-Request-ID`.

## Paso 8: Tests y Lint

```bash
docker compose -f docker-compose.test.yml up -d --wait   # MariaDB de test en 127.0.0.1:3307
uv run pytest
docker compose -f docker-compose.test.yml down

uv run ruff check .
uv run ruff format .

uv run --with pre-commit pre-commit install              # hooks: ruff, detect-secrets
```

Los tests marcados `db` se omiten automáticamente si la MariaDB de test no está disponible. Las variables `TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`, `TEST_DB_PASS`, `TEST_DB_NAME` permiten apuntar a otra instancia.

- `tests/conftest.py` fija `ENV_FILE=""`: tu `.env` local nunca afecta a los tests.
- La fixture de esquema **borra todas las tablas** de la BD de test y aplica `database/init/*.sql` + `database/procedures/*.sql`.
- `filterwarnings` convierte en error `DeprecationWarning`, `FastAPIDeprecationWarning`, `StarletteDeprecationWarning`, `UvicornDeprecationWarning` y `RuntimeWarning` (corrutinas sin `await`).

## Solución de Problemas

### `Configuración inválida (...): APP_ENV: es obligatorio`

No existe `.env` o no define `APP_ENV`: `cp .env.example .env`.

### `Configuración inválida: SECRET_KEY debe tener al menos 32 caracteres...`

Con `APP_ENV=production` la configuración se valida estrictamente. Generar una clave:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### `/ready` responde 503 / `Base de datos no disponible`

Revisar `DB_HOST`, `DB_PORT`, credenciales y que el servidor esté arriba. Errores `Access denied for user` indican usuario/permisos.

### `ModuleNotFoundError: No module named 'app'`

Ejecutar siempre desde la raíz del proyecto con `uv run`.

### `Table '...users' doesn't exist`

Falta aplicar los scripts de `database/init/` (ver "Crear el esquema"). En Docker, los scripts solo corren con un volumen vacío: `docker compose down -v` en local, o aplicarlos a mano con `mariadb ... < database/init/NNN_x.sql`.

### Puerto 8000 en uso

```bash
lsof -i :8000                           # Linux / macOS
uv run fastapi dev --port 8001
```

## Próximos Pasos

1. [Estructura del Proyecto](project-structure.md)
2. [Mejores Prácticas (async)](development/best-practices.md)
3. [Base de Datos](features/database.md)
4. [Respuestas Estándar](features/response-format.md) y [Excepciones](features/exceptions.md)
5. [Despliegue con Docker](docker-deployment.md)
