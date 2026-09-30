# Contexto de Request (ContextVars)

`app/core/context.py` define ContextVars con datos de la request en curso. Se pueden leer desde cualquier parte del código (controllers, models, logging, handlers) sin pasarlos como argumento. En código async viajan solos entre `await`.

Su uso principal es la **auditoría**: registrar quién hizo qué, desde dónde y en qué ruta sin pasar el `request` por todas las capas (ver [Auditoría](#auditoría)).

Los establece `ContextMiddleware`, que es el middleware más externo de la **app raíz**, y los resetea al terminar la request.

## Variables disponibles

```python
from app.core.context import (
    current_http_identifier,     # str | None       — Request ID
    current_request_ip,          # str | None       — IP del cliente (scope["client"])
    current_request_method,      # str | None       — GET, POST...
    current_request_route,       # str | None       — path real: /api/v1/users/15
    current_request_host,        # str | None       — header Host
    current_request_user_agent,  # str | None       — header User-Agent
    current_user_id,             # str | int | None — lo establece tu capa de auth
    get_request_id,              # () -> str | None — atajo de current_http_identifier.get()
)
```

`current_request_route` guarda el **path real**, no la plantilla (`/users/{user_id}`).

Fuera de una request (scripts, lifespan) todas valen `None`.

## Request ID

- Si llega un `X-Request-ID` válido (`[A-Za-z0-9._:-]{8,128}`), se reutiliza. nginx envía su `$request_id`, así que la misma traza aparece en el log de nginx y en el de la API.
- Si no llega o es inválido, se genera uno con `secrets.token_hex(8)` (16 caracteres hex).
- Siempre se devuelve en el header de respuesta `X-Request-ID`, también en los errores.
- Se incluye en el body de todo error: `detail.request_id`.
- También se guarda en `request.state.request_id`, que sigue disponible aunque los ContextVars ya se hayan reseteado (lo usa el handler de 500).

```python
from fastapi import Request


@router.get("/debug")
async def debug(request: Request):
    return success(data={"request_id": request.state.request_id})
```

## Logging

No hace falta agregar el request id a mano: `configure_logging` lo inyecta en cada línea (y `user_id` en formato JSON).

```python
import logging

logger = logging.getLogger(__name__)
logger.info("Pedido %s confirmado", order_id)
# 2026-09-29 10:30:15,123 [INFO] app.controllers.order_controller [a1b2c3d4e5f6a7b8] Pedido 42 confirmado
```

Ver [Logging](logging.md).

## Establecer el usuario actual

El template no incluye autenticación. Cuando la agregues, establece `current_user_id` desde una **dependencia `async def`**:

```python
from typing import Annotated

from fastapi import Depends, Request

from app.core.context import current_user_id
from app.exceptions import AppHttpException


async def get_current_user_id(request: Request) -> int:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AppHttpException(
            "No autenticado", 401, code="unauthenticated", headers={"WWW-Authenticate": "Bearer"}
        )
    user_id = await verify_token(auth.removeprefix("Bearer "))  # implementación del proyecto
    current_user_id.set(user_id)
    return user_id


CurrentUserDep = Annotated[int, Depends(get_current_user_id)]
```

Tiene que ser `async def`: las dependencias `def` corren en un thread con una copia del contexto, y un `.set()` hecho ahí no se ve fuera. Como los middlewares son ASGI puros (sin `BaseHTTPMiddleware`), el valor que fija una dependencia async queda visible para el resto de la request, incluido el access log.

`ContextMiddleware` pone `current_user_id` en `None` al empezar cada request.

## Auditoría

Ejemplo de un model que registra cambios en una tabla `audit_log` con los datos de la request en curso:

```python
from app.core.context import current_request_ip, current_user_id, get_request_id
from app.core.database import Database


class AuditModel:
    def __init__(self, db: Database):
        self.db = db

    async def log(self, action: str, target_id: int) -> None:
        await self.db.execute(
            "INSERT INTO audit_log (action, user_id, target_id, ip, request_id) "
            "VALUES (:action, :user_id, :target_id, :ip, :request_id)",
            {
                "action": action,
                "user_id": current_user_id.get(),
                "target_id": target_id,
                "ip": current_request_ip.get(),
                "request_id": get_request_id(),
            },
        )
```

## Buenas prácticas

- **Solo lectura fuera de la capa de auth.** Los valores de request los fija el middleware. Solo `current_user_id` lo fija tu dependencia de autenticación.
- **Validar `None`** en operaciones críticas: fuera de una request, o sin auth, las variables valen `None`.
- **IP real detrás de un proxy:** `current_request_ip` sale de `scope["client"]`. Para que sea la IP real, uvicorn corre con `--proxy-headers --forwarded-allow-ips=<IP del proxy>` (ya configurado en `docker/scripts/entrypoint.sh` con `FORWARDED_ALLOW_IPS`). Nunca uses `*`.

## Agregar una variable

1. Declararla en `app/core/context.py`:

   ```python
   current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)
   ```

2. Establecerla desde la dependencia o middleware que tenga el dato. Si es un dato de la request (header, path), agrégala a `ContextMiddleware` junto a su `reset` en el `finally`.

---

Ver también: [Middlewares](middlewares.md) · [Logging](logging.md)
