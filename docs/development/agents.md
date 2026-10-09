# Agentes de IA del proyecto

Las definiciones están en `.agents/agents/`. Claude Code no las registra como subagentes: son guías que se leen bajo
demanda con `Read` (no importarlas con `@`, para no cargarlas en cada sesión).

| Agente | Archivo | Cuándo leerlo |
|---|---|---|
| `python-pro` | `.agents/agents/python-pro.md` | Antes de escribir o modificar código Python |
| `python-development-fastapi-pro` | `.agents/agents/python-development-fastapi-pro.md` | Antes de crear o cambiar endpoints, middlewares, dependencias o arquitectura de la API |

Un agente nuevo se agrega en `.agents/agents/` y a esta tabla.

## Precedencia

`AGENTS.md` y `docs/development/` mandan sobre los agentes. Los agentes son genéricos y asumen un stack más
amplio: si chocan (docstrings, `mypy --strict`, metas de cobertura, versión de Python, herramientas fuera del stack),
se aplica lo del proyecto.

## Qué no aplica de los agentes en este proyecto

- **ORM:** SQLAlchemy se usa solo como engine y pool async. No hay modelos declarativos, `Session`, repository ni unit of
  work: el acceso a datos es SQL directo con `Database` (`app/core/database.py`) y `asyncmy` (no `asyncpg`).
- **Migraciones:** el esquema va en SQL plano (`database/`); Alembic es opcional y no hay migraciones aplicadas.
- **Arquitectura:** capas estrictas Routes → Controllers → Services → Models (verificadas por `tests/test_architecture.py`);
  no CQRS, event sourcing ni microservicios.
- **Respuestas y errores:** siempre `ApiResponse[T]` y `AppHttpException` (nunca `HTTPException`).
- **Paginación, filtros y orden:** estándar `page`/`size` (offset) con `ListQuery`, `WhereBuilder` y `order_by`;
  no crear helpers propios ni parámetros sueltos. Cursor solo como excepción justificada (ver `docs/features/pagination.md`).
- **Librerías:** no se usan `loguru`/`structlog` (logging estándar con formato JSON), `python-jose` ni `asyncpg`.
- **Docstrings:** no son obligatorios (criterio en [Tests y calidad](testing-and-quality.md)).
- **Calidad:** el type checker es pyright (no mypy) y no hay umbral de cobertura ni CI configurado.
