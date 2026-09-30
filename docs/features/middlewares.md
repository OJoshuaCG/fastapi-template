# Middlewares

Todos los middlewares propios son **ASGI puros**, sin `BaseHTTPMiddleware`. Así:

- no agregan task groups extra por request,
- no bufferean la respuesta, y el streaming (`StreamingResponse`, SSE) pasa sin cambios,
- los ContextVars que fija una dependencia async son visibles para el resto del stack.

## Stack completo

El último middleware agregado con `add_middleware` es el más externo.

```
Request
  │
  ▼  App raíz (main.py)
  ServerErrorMiddleware        (Starlette) 500 de último recurso
  ContextMiddleware            request id + ContextVars
  LoggerMiddleware             access log (si LOGGER_MIDDLEWARE_ENABLED)
  CORSMiddleware               si CORS_ORIGINS no está vacío
  ExceptionMiddleware          (Starlette) handlers de la app raíz
  Router ── /health, /ready
         └─ Mount /api/v1
              │
              ▼  Sub-app v1 (create_versioned_app)
              ServerErrorMiddleware
              RequestSizeMiddleware    límite de body
              ExceptionMiddleware      handlers de la versión
              Router → dependencias globales (rate limit) → dependencias de ruta → endpoint
```

Por eso `/health` y `/ready` llevan request id y CORS, pero no pasan por el límite de body ni por el rate limit, y el access log las excluye.

## ContextMiddleware

`app/middleware/ContextMiddleware.py`, en la app raíz.

- Acepta un `X-Request-ID` entrante si es válido (`[A-Za-z0-9._:-]{8,128}`). Si no, genera uno (`secrets.token_hex(8)`).
- Establece los ContextVars de `app/core/context.py` y los resetea en el `finally`.
- Guarda el id en `scope["state"]["request_id"]` (`request.state.request_id`).
- Agrega `X-Request-ID` a la respuesta.

Ver [Contexto de Request](context.md).

## LoggerMiddleware

`app/middleware/LoggerMiddleware.py`, en la app raíz. Solo se agrega si `LOGGER_MIDDLEWARE_ENABLED=True`.

Escribe una línea por request (IP, método, path, status, duración) con nivel según el status. Excluye `/health` y `/ready`. **Nunca registra el body.** Enmascara query params y headers sensibles. Ver [Logging](logging.md#access-log-loggermiddleware).

## CORSMiddleware

El `CORSMiddleware` de Starlette, en la app raíz. Ver [CORS](cors.md).

## RequestSizeMiddleware

`app/middleware/RequestSizeMiddleware.py`, agregado por `create_versioned_app()` en **cada sub-app** como `RequestSizeMiddleware(app, max_bytes=...)`.

1. `Content-Length` mayor al límite: **413** JSON inmediato, sin leer el body. `Content-Length` no numérico: **400**.
2. Bodies chunked o sin `Content-Length`: delega en `RequestBodyLimitMiddleware` de Starlette, que cuenta los bytes a medida que llegan (sin cargar el body en memoria) y lanza un `HTTPException` 413 que el handler formatea como JSON estándar.

```json
{"detail": {"msg": "El cuerpo de la solicitud supera el límite de 10MB", "type": "ContentTooLarge", "request_id": "…"}}
```

El límite es uno solo para toda la versión (no hay overrides por ruta):

```env
# Mantener igual a client_max_body_size de nginx
REQUEST_MAX_SIZE_MB=10
```

Para un endpoint que necesite bodies más grandes (ej. subida de archivos), sube ambos límites: `REQUEST_MAX_SIZE_MB` y `client_max_body_size` de nginx.

## Agregar un middleware propio

Usa la forma ASGI pura:

```python
# app/middleware/SecurityHeadersMiddleware.py
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
            await send(message)

        await self.app(scope, receive, send_with_headers)
```

Para responder un error con el formato estándar desde un middleware:

```python
from app.exceptions import error_response

await error_response(403, "Acceso denegado", code="ip_blocked")(scope, receive, send)
return
```

### Dónde registrarlo

- **Transversal (todas las versiones):** en `create_app()` de `main.py`, **antes** de `app.add_middleware(ContextMiddleware)`, para que quede dentro de Context y tenga el request id disponible.
- **Solo una versión:** con `versioned.add_middleware(...)` en `create_versioned_app()`, o sobre la sub-app en `main.py`.

### Middleware o dependencia

La autenticación, la autorización y el rate limit por ruta van mejor como **dependencias**. Se declaran por ruta, aparecen en OpenAPI y se reemplazan en tests con `dependency_overrides`. Reserva los middlewares para lo que aplica a todo el tráfico y no depende de la ruta (headers, request id, límites de body).

> Evita `BaseHTTPMiddleware` y `@app.middleware("http")`: bufferean mal el streaming y aíslan los ContextVars.

---

Ver también: [API Versionada](api-versioning.md)
