# API Versionada

Cada versión de la API es una **sub-app FastAPI** montada en la app raíz. Cada versión tiene su propia documentación, sus rutas y su límite de body, así que v1 y v2 pueden convivir sin afectarse.

## Estructura

```
main.py → create_app()               App raíz (sin docs propios)
├── GET /health                      liveness
├── GET /ready                       readiness (BD)
├── /api/v1 → create_versioned_app("v1")
│   ├── /docs, /redoc, /openapi.json
│   ├── /users/...
│   └── /test/...                    solo fuera de producción
└── /api/v2 → (cuando haga falta)
```

## Qué vive en cada nivel

| App raíz (`main.py`) | Sub-app versionada (`create_versioned_app`) |
|---|---|
| `ContextMiddleware` (request id, ContextVars) | Rutas de la versión |
| `LoggerMiddleware` (access log) | Documentación (`/docs`, `/redoc`) |
| `CORSMiddleware` | `RequestSizeMiddleware` (límite de body) |
| Handlers de error (`register_exception_handlers`) | Handlers de error (`register_exception_handlers`) |
| Lifespan: engine BD, cliente HTTP | |
| `/health`, `/ready` | |

> **Starlette no ejecuta el lifespan de las sub-apps montadas.** Todo recurso con ciclo de vida (BD, clientes, tareas) se inicia y se cierra en el lifespan de la app raíz.

Los handlers de error se registran en los dos niveles para que cualquier error (un 404 en la raíz o un 422 dentro de v1) tenga el mismo formato.

## `create_versioned_app()`

```python
def create_versioned_app(version: str) -> FastAPI:
```

- `version`: `"v1"`, `"v2"`... Se usa en el título (`"{APP_NAME} V1"`).

Además configura:

- `RequestSizeMiddleware` con `REQUEST_MAX_SIZE_MB` para toda la versión (sin overrides por ruta). Ver [Middlewares](middlewares.md#requestsizemiddleware).
- `generate_unique_id_function`: operation ids `"{Tag}-{nombre_función}"` (ej. `Users-get_user`), para que los clientes generados desde OpenAPI tengan nombres limpios.
- Documentación según `DOCS_ENABLED` / `DOCS_PASSWORD_ENABLED` (abajo).
- `telemetry=telemetry_config()`: la misma configuración de OpenTelemetry que la app raíz (`telemetry_config()` vive en `app/core/versioned_app.py` y se aplica a las dos).

La configuración sale del singleton `settings` (`from app.core.environment import settings`): ni `create_app()`, ni `create_versioned_app()`, ni `build_v1_router()` reciben `settings`. En tests se cambia con `monkeypatch.setattr(settings, "X", valor)` (se revierte solo).

## Registrar rutas

Cada versión expone una función que construye su router:

```python
# app/routes/v1/routes.py
from fastapi import APIRouter

from app.core.environment import settings
from app.routes.v1 import test, users


def build_v1_router() -> APIRouter:
    router = APIRouter()
    router.include_router(users.router)

    # Endpoints de ejemplo/diagnóstico: nunca en producción
    if not settings.is_production:
        router.include_router(test.router)
    return router
```

Para una feature nueva, crea `app/routes/v1/posts.py` con `router = APIRouter(prefix="/posts", tags=["Posts"])` y agrégalo con `router.include_router(posts.router)`.

## Montaje en `main.py`

```python
v1 = create_versioned_app("v1")
v1.include_router(build_v1_router())
app.mount("/api/v1", v1)

app.state.versioned_apps = {"v1": v1}
```

### Agregar v2

1. Crear `app/routes/v2/` con sus routers y `build_v2_router()`.
2. En `create_app()`:

   ```python
   v2 = create_versioned_app("v2")
   v2.include_router(build_v2_router())
   app.mount("/api/v2", v2)

   app.state.versioned_apps = {"v1": v1, "v2": v2}
   ```

v2 puede reutilizar los controllers y models de v1. Normalmente solo cambian los schemas y las routes.

## Documentación

| `DOCS_ENABLED` | `DOCS_PASSWORD_ENABLED` | Resultado |
|---|---|---|
| vacío | — | habilitada fuera de producción, deshabilitada en producción |
| `True` | `False` | `/api/v1/docs`, `/api/v1/redoc`, `/api/v1/openapi.json` públicos (en producción se registra un warning al arrancar) |
| `True` | `True` | las tres rutas piden **HTTP Basic** (`DOCS_USER` / `DOCS_PASSWORD`); en staging y producción el password debe tener ≥ 12 caracteres |
| `False` | — | sin documentación |

La app raíz no tiene docs (`/docs` responde 404).

## Tests y `dependency_overrides`

Los `dependency_overrides` son **por app**. Las rutas viven en la sub-app, así que los overrides de sus dependencias se aplican ahí, a través de `app.state.versioned_apps`:

```python
from app.controllers.user_controller import get_user_controller


async def test_controller_can_be_overridden(client, v1_app):  # v1_app = app.state.versioned_apps["v1"]
    class FakeController:
        async def get_user(self, user_id: int) -> dict: ...

    v1_app.dependency_overrides[get_user_controller] = FakeController
    try:
        resp = await client.get("/api/v1/users/99")
    finally:
        v1_app.dependency_overrides.clear()
```

Las rutas de la app raíz (`/health`, `/ready`) se reemplazan en la app raíz: `app.dependency_overrides[get_database] = ...`. Ver `tests/conftest.py`.

---

Ver también: [Middlewares](middlewares.md) · [Rate Limiting](rate-limiting.md)
