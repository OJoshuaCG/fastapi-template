# FastAPI Template - Guía para Agentes de IA

Plantilla base para nuevos proyectos FastAPI: **async de punta a punta**, MariaDB/MySQL, sub-apps versionadas,
formato de respuesta y de error estándar, tests contra BD real.

## Reglas de oro

- Nada bloqueante dentro de `async def` (BD con `await db.*`, HTTP con `ServiceClient`, archivos con `anyio`).
- Capas: **Routes → Controllers → (Services) → Models → Database**. Sin ORM: SQL directo con parámetros.
- Todo endpoint usa `ApiResponse[T]`; todo error controlado usa `AppHttpException` (nunca `HTTPException`).
- Toda configuración sale de `settings` (`app/core/environment.py`) y de `.env.example`; nunca secretos en código ni logs.
- Contrato de API único para todos los endpoints (`docs/development/api-contract.md`): id en el path; paginación
  (`page`/`size`), filtros, fechas (`<campo>_from`/`<campo>_to`) y orden (`sort=-campo`) en query; escritura en body.
- Todo listado `GET` usa los helpers del contrato, sin reimplementarlos: recibe **un solo**
  `Annotated[XxxListQuery, Query()]` (hereda de `ListQuery`, `app/utils/list_query.py`) y el model arma el SQL con
  `WhereBuilder` y `order_by` (`app/core/sql_filters.py`). `tests/test_architecture.py` falla si un listado recibe
  query params sueltos. Receta: `docs/features/pagination.md`.
- Actualizar la documentación en el mismo cambio que el código.

## Dónde leer más

**`docs/development/`**: reglas de programación detalladas. Léelas **bajo demanda** según la tarea
(índice en [`docs/development/README.md`](docs/development/README.md)):

| Si vas a… | Lee |
|---|---|
| Escribir código o crear archivos nuevos | `architecture.md` |
| Usar o agregar variables de entorno | `configuration.md` |
| Escribir models, consultas o stored procedures | `data-access.md` |
| Crear una feature completa | `new-feature.md` |
| Consumir una API externa | `external-services.md` |
| Cifrar, contraseñas, IDs públicos | `security.md` |
| Diseñar o cambiar un endpoint (contrato) | `api-contract.md` y `api-conventions.md` |
| Escribir tests o verificar calidad | `testing-and-quality.md` |
| Iniciar un proyecto o quitar el código de ejemplo | `starting-new-project.md` |

**`docs/`**: guía del proyecto. Úsala para entender qué hace cada pieza y aprovechar lo que ya incluye la plantilla:

- `docs/features/`: una página por funcionalidad (base de datos, services, seguridad, errores, logging, rate limiting,
  paginación, uploads, versionado, middlewares...).
- `docs/development/best-practices.md`: buenas prácticas y diagnóstico (async, rendimiento).
- `docs/getting-started.md`, `docs/project-structure.md`, `docs/deployment.md`, `docs/docker-deployment.md`.
- La plantilla no tiene lógica de negocio de dominio propia; cuando un proyecto la tenga, se documenta en `docs/`.

## Comandos

```bash
cp .env.example .env && uv sync --all-groups
uv run fastapi dev                                       # desarrollo con reload
docker compose -f docker-compose.test.yml up -d --wait   # MariaDB de test (puerto 3307)
uv run ruff check . && uv run ruff format --check .      # lint y formato
uv run pyright                                           # tipos
uv run pip-audit                                         # vulnerabilidades en dependencias
uv run pytest --cov                                      # tests con cobertura (solo cuando se pida)
```

## Stack

FastAPI · Starlette · SQLAlchemy asyncio (solo engine/pool) + asyncmy · Pydantic v2 + pydantic-settings · httpx ·
limits · cryptography · sqids · uvicorn · pytest-asyncio + httpx2 · Ruff · pyright · pytest-cov · pip-audit · uv ·
Python ≥3.13. Versiones exactas en `pyproject.toml`.

## Agentes

Definiciones genéricas en `.agents/agents/` (`python-pro`, `python-development-fastapi-pro`): guías que se leen bajo
demanda, no subagentes registrados. **Este documento y `docs/development/` mandan sobre ellos.** Qué no aplica y
cómo usarlos: [`docs/development/agents.md`](docs/development/agents.md).
