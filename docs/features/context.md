# Context Management

El sistema de Context Management utiliza ContextVars de Python para mantener información de estado de cada request a través de toda la aplicación, similar a las sesiones en PHP.

## ¿Qué es Context Management?

En aplicaciones asíncronas como FastAPI, cada request se maneja en su propio contexto aislado. ContextVars permite almacenar variables que se mantienen durante toda la vida de una request sin necesidad de pasarlas como parámetros.

### Ventajas

- **Trazabilidad**: Request ID único para cada petición
- **Debugging**: Correlacionar logs de una misma request
- **Información contextual**: Acceso a IP, método HTTP, ruta, usuario actual desde cualquier parte del código
- **Thread-safe**: Cada request async tiene su propio contexto aislado

## Arquitectura

### Componentes

1. **`app/core/context.py`**: Define las ContextVars disponibles
2. **`app/middleware/ContextMiddleware.py`**: Establece y limpia valores automáticamente

## ContextVars Disponibles

### Variables de Request

```python
# app/core/context.py
from contextvars import ContextVar

# Request ID único generado para cada petición
current_http_identifier: ContextVar[str | None] = ContextVar("current_http_identifier", default=None)

# Información de la request
current_request_ip: ContextVar[str | None] = ContextVar("current_request_ip", default=None)
current_request_method: ContextVar[str | None] = ContextVar("current_request_method", default=None)
current_request_route: ContextVar[str | None] = ContextVar("current_request_route", default=None)
current_request_client_host: ContextVar[str | None] = ContextVar("current_request_client_host", default=None)
current_request_host: ContextVar[str | None] = ContextVar("current_request_host", default=None)
current_request_user_agent: ContextVar[str | None] = ContextVar("current_request_user_agent", default=None)

# Usuario actual (se establece en middleware de autenticación)
current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
```

## Uso Básico

### Leer Valores

```python
from app.core.context import current_http_identifier, current_request_ip, current_user_id

# En cualquier parte del código (endpoints, servicios, utils)
request_id = current_http_identifier.get()
client_ip = current_request_ip.get()
user_id = current_user_id.get()

print(f"Request {request_id} desde {client_ip} por usuario {user_id}")
```

### Establecer Valores

**Nota**: Solo debes establecer valores en middlewares o funciones de autenticación.

```python
from app.core.context import current_user_id

# En middleware de autenticación
@router.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Autenticar usuario
    user = authenticate(request)

    if user:
        current_user_id.set(user.id)

    response = await call_next(request)
    return response
```

## ContextMiddleware

Este middleware establece automáticamente las variables de contexto para cada request.

### Funcionamiento

```python
# app/middleware/ContextMiddleware.py
class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Generar Request ID único
        request_id = secrets.token_hex(8)  # Ej: "a1b2c3d4e5f6g7h8"

        # 2. Establecer ContextVars
        token_id = current_http_identifier.set(request_id)
        token_ip = current_request_ip.set(request.client.host if request.client else "unknown")
        token_method = current_request_method.set(request.method)
        token_route = current_request_route.set(request.url.path)
        token_client_host = current_request_client_host.set(request.client.host if request.client else None)
        token_host = current_request_host.set(request.url.hostname)
        token_user_agent = current_request_user_agent.set(request.headers.get("user-agent"))

        # 3. Inyectar en request.state (acceso desde request object)
        request.state.request_id = request_id

        try:
            response = await call_next(request)

            # 4. Inyectar header X-Request-ID en respuesta
            response.headers["X-Request-ID"] = request_id

            return response

        finally:
            # 5. Limpieza de ContextVars (previene memory leaks)
            current_http_identifier.reset(token_id)
            current_request_ip.reset(token_ip)
            # ... resto de resets
```

### Request ID

El Request ID es un identificador único generado para cada petición:

- **Formato**: 16 caracteres hexadecimales (ej: `a1b2c3d4e5f6g7h8`)
- **Generación**: `secrets.token_hex(8)` - criptográficamente seguro
- **Propósito**: Correlacionar logs, debugging, trazabilidad

## Ejemplos de Uso

### Logging con Request ID

```python
from fastapi import APIRouter
from app.core.logger import get_logger
from app.core.context import current_http_identifier

router = APIRouter()
logger = get_logger(__name__)

@router.post("/users")
async def create_user(user: UserCreate):
    request_id = current_http_identifier.get()

    logger.info(f"{request_id} | Iniciando creación de usuario: {user.username}")

    # ... lógica de creación

    logger.info(f"{request_id} | Usuario creado exitosamente: ID {new_user.id}")
    return new_user
```

**Logs generados:**

```
2026-02-11 10:30:15 [INFO] a1b2c3d4e5f6g7h8 | Iniciando creación de usuario: john
2026-02-11 10:30:15 [INFO] a1b2c3d4e5f6g7h8 | Usuario creado exitosamente: ID 123
```

Ahora puedes buscar todos los logs de esta request con `grep a1b2c3d4e5f6g7h8`.

### Auditoría con IP y Usuario

```python
from app.core.context import current_http_identifier, current_request_ip, current_user_id

@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    request_id = current_http_identifier.get()
    client_ip = current_request_ip.get()
    current_user = current_user_id.get()

    logger.warning(
        f"{request_id} | Usuario {current_user} desde {client_ip} "
        f"eliminó usuario ID {user_id}"
    )

    # ... lógica de eliminación

    # Guardar en tabla de auditoría
    db.execute_query(
        "INSERT INTO audit_log (action, user_id, target_id, ip, request_id) "
        "VALUES (:action, :user_id, :target_id, :ip, :request_id)",
        {
            "action": "DELETE_USER",
            "user_id": current_user,
            "target_id": user_id,
            "ip": client_ip,
            "request_id": request_id
        }
    )
```

### Validación de Usuario Actual

```python
from app.core.context import current_user_id
from app.exceptions import AppHttpException

@router.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate):
    current_user = current_user_id.get()

    # Validar que el usuario solo pueda editar su propio perfil
    if current_user != user_id:
        raise AppHttpException(
            message="No tienes permisos para editar este usuario",
            status_code=403,
            context={"current_user": current_user, "target_user": user_id}
        )

    # ... lógica de actualización
```

### Rate Limiting por IP

```python
from app.core.context import current_request_ip
import time

# Cache simple (en producción usar Redis)
request_counts = {}

@router.post("/api/public-endpoint")
async def public_endpoint():
    client_ip = current_request_ip.get()
    current_time = time.time()

    # Limpiar entradas antiguas
    request_counts = {
        ip: (count, timestamp)
        for ip, (count, timestamp) in request_counts.items()
        if current_time - timestamp < 60
    }

    # Verificar rate limit (10 requests por minuto)
    if client_ip in request_counts:
        count, timestamp = request_counts[client_ip]
        if count >= 10:
            raise AppHttpException(
                message="Rate limit excedido",
                status_code=429,
                context={"ip": client_ip}
            )
        request_counts[client_ip] = (count + 1, timestamp)
    else:
        request_counts[client_ip] = (1, current_time)

    # ... lógica del endpoint
```

## Integración con Autenticación

### Middleware de Autenticación

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.context import current_user_id

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Obtener token del header
        auth_header = request.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

            # Decodificar token y obtener user_id
            user = decode_token(token)  # Implementar según tu sistema de auth

            if user:
                # Establecer usuario actual en contexto
                current_user_id.set(user.id)

        response = await call_next(request)
        return response
```

Registrar en `main.py`:

```python
from app.middleware.AuthMiddleware import AuthMiddleware

app.add_middleware(AuthMiddleware)
app.add_middleware(ContextMiddleware)  # Debe ir después de AuthMiddleware
```

### Dependency para Rutas Protegidas

```python
from fastapi import Depends, HTTPException
from app.core.context import current_user_id

def get_current_user():
    user_id = current_user_id.get()

    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    return user_id

@router.get("/profile")
async def get_profile(user_id: int = Depends(get_current_user)):
    # user_id es el ID del usuario autenticado
    user = db.execute_query(
        "SELECT * FROM users WHERE id = :id",
        {"id": user_id},
        fetchone=True
    )
    return user
```

## Acceso desde Request Object

Además de ContextVars, el Request ID está disponible en `request.state`:

```python
from fastapi import Request

@router.get("/")
async def endpoint(request: Request):
    request_id = request.state.request_id
    print(f"Request ID: {request_id}")
```

## Response Header X-Request-ID

Cada respuesta incluye el header `X-Request-ID`:

```bash
curl -I http://localhost:8000/users
# HTTP/1.1 200 OK
# X-Request-ID: a1b2c3d4e5f6g7h8
# ...
```

Esto permite al cliente correlacionar errores:

```javascript
// Frontend
fetch('/api/users')
  .then(res => {
    if (!res.ok) {
      const requestId = res.headers.get('X-Request-ID');
      console.error(`Error en request ${requestId}`);
      // Reportar error con Request ID al soporte
    }
  });
```

## Buenas Prácticas

### 1. Solo Lectura en Endpoints

```python
# ✅ Correcto (solo lectura)
from app.core.context import current_user_id

user_id = current_user_id.get()

# ❌ Incorrecto (establecer en endpoint)
current_user_id.set(123)  # NO hacer esto en endpoints
```

**Razón**: Los valores deben establecerse solo en middlewares para evitar inconsistencias.

### 2. Siempre Incluir Request ID en Logs

```python
# ✅ Correcto
request_id = current_http_identifier.get()
logger.info(f"{request_id} | Procesando pago")

# ❌ Incorrecto
logger.info("Procesando pago")  # Sin Request ID
```

### 3. Validar None en Operaciones Críticas

```python
# ✅ Correcto
user_id = current_user_id.get()
if user_id is None:
    raise AppHttpException("No autenticado", status_code=401)

# ❌ Incorrecto
user_id = current_user_id.get()
# Usar user_id sin validar (puede ser None)
```

### 4. No Confiar Ciegamente en Variables de Contexto

```python
# ⚠️ Cuidado
client_ip = current_request_ip.get()
# IP puede ser spoofed si estás detrás de un proxy

# ✅ Mejor
# Configurar proxy headers correctamente (X-Forwarded-For, X-Real-IP)
# y validar en middleware
```

## Debugging

### Ver Valores de Contexto

```python
from app.core.context import *

@router.get("/debug/context")
async def debug_context():
    return {
        "request_id": current_http_identifier.get(),
        "ip": current_request_ip.get(),
        "method": current_request_method.get(),
        "route": current_request_route.get(),
        "user_agent": current_request_user_agent.get(),
        "user_id": current_user_id.get(),
    }
```

### Buscar Logs por Request ID

```bash
# En logs de archivo
cat app.log | grep a1b2c3d4e5f6g7h8

# En logs de consola (tiempo real)
uv run uvicorn main:app --reload | grep a1b2c3d4e5f6g7h8
```

## Extensión: Agregar Nuevas ContextVars

Si necesitas agregar más variables de contexto:

1. **Definir en `app/core/context.py`:**

```python
current_organization_id: ContextVar[int | None] = ContextVar(
    "current_organization_id",
    default=None
)
```

2. **Establecer en middleware:**

```python
# app/middleware/AuthMiddleware.py
from app.core.context import current_organization_id

# Después de autenticar
current_organization_id.set(user.organization_id)
```

3. **Usar en endpoints:**

```python
from app.core.context import current_organization_id

org_id = current_organization_id.get()
```

## Recursos

- [Python ContextVars Documentation](https://docs.python.org/3/library/contextvars.html)
- [Sistema de Logging](logging.md) - Para usar Request ID en logs
- [Middlewares](middlewares.md) - ContextMiddleware
- [Manejo de Excepciones](exceptions.md)

---

**Siguiente**: [Base de Datos](database.md)
