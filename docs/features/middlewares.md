# Middlewares

Los middlewares interceptan requests y responses para agregar funcionalidad transversal como logging, autenticación, CORS, etc.

## Middlewares Disponibles

### 1. ContextMiddleware

**Ubicación**: `app/middleware/ContextMiddleware.py`

**Propósito**: Gestión de contexto de requests (Request ID, ContextVars)

**Funcionalidad:**
- Genera Request ID único para cada petición
- Establece ContextVars con información de la request
- Inyecta Request ID en request.state
- Agrega header `X-Request-ID` a responses
- Limpia ContextVars al finalizar

**Configuración en main.py:**

```python
from app.middleware.ContextMiddleware import ContextMiddleware

app.add_middleware(ContextMiddleware)
```

**Ver más**: [Context Management](context.md)

### 2. LoggerMiddleware

**Ubicación**: `app/middleware/LoggerMiddleware.py`

**Propósito**: Logging automático de requests/responses

**Funcionalidad:**
- Registra método, path, query params, body
- Registra status code y tiempo de procesamiento
- Usa Request ID para correlación
- Oculta información sensible en rutas específicas
- Opcionalmente registra headers

**Configuración:**

```env
# .env
LOGGER_MIDDLEWARE_ENABLED=True
LOGGER_MIDDLEWARE_SHOW_HEADERS=False
```

```python
# main.py
from app.core.environments import LOGGER_MIDDLEWARE_ENABLED
from app.middleware.LoggerMiddleware import LoggerMiddleware

if LOGGER_MIDDLEWARE_ENABLED:
    app.add_middleware(LoggerMiddleware)
```

**Ver más**: [Sistema de Logging](logging.md)

## Orden de Middlewares

**IMPORTANTE**: El orden de registro de middlewares es inverso al orden de ejecución.

```python
# main.py
if LOGGER_MIDDLEWARE_ENABLED:
    app.add_middleware(LoggerMiddleware)  # Se ejecuta SEGUNDO (logging)
app.add_middleware(ContextMiddleware)     # Se ejecuta PRIMERO (genera Request ID)
```

**Flujo de ejecución:**

```
Request
  ↓
ContextMiddleware (genera Request ID)
  ↓
LoggerMiddleware (registra request usando Request ID)
  ↓
Router/Endpoint
  ↓
LoggerMiddleware (registra response)
  ↓
ContextMiddleware (inyecta X-Request-ID header, limpia ContextVars)
  ↓
Response
```

## Crear Middleware Personalizado

### Ejemplo: Rate Limiting Middleware

```python
# app/middleware/RateLimitMiddleware.py
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.context import current_request_ip
from app.exceptions import AppHttpException

# Cache simple (en producción usar Redis)
request_counts = {}

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()

        # Limpiar entradas antiguas (>60 segundos)
        global request_counts
        request_counts = {
            ip: (count, timestamp)
            for ip, (count, timestamp) in request_counts.items()
            if current_time - timestamp < 60
        }

        # Verificar rate limit (60 requests por minuto)
        if client_ip in request_counts:
            count, timestamp = request_counts[client_ip]
            if count >= 60:
                raise AppHttpException(
                    message="Rate limit excedido. Intenta más tarde.",
                    status_code=429,
                    context={"ip": client_ip}
                )
            request_counts[client_ip] = (count + 1, timestamp)
        else:
            request_counts[client_ip] = (1, current_time)

        response = await call_next(request)
        return response
```

**Registrar en main.py:**

```python
from app.middleware.RateLimitMiddleware import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
```

### Ejemplo: Authentication Middleware

```python
# app/middleware/AuthMiddleware.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.context import current_user_id
from app.exceptions import AppHttpException

PROTECTED_ROUTES = ["/profile", "/users/me", "/admin"]

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Rutas públicas
        if request.url.path not in PROTECTED_ROUTES:
            return await call_next(request)

        # Obtener token del header
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            raise AppHttpException(
                message="No autenticado",
                status_code=401
            )

        token = auth_header.split(" ")[1]

        # Decodificar token (implementar según tu sistema)
        user = decode_jwt_token(token)

        if not user:
            raise AppHttpException(
                message="Token inválido",
                status_code=401
            )

        # Establecer usuario en contexto
        current_user_id.set(user.id)

        response = await call_next(request)
        return response
```

### Ejemplo: CORS Middleware

FastAPI incluye middleware de CORS nativo:

```python
# main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://miapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Configuración por entorno:**

```python
from app.core.environments import APP_ENV

if APP_ENV == "development":
    origins = ["*"]  # Permitir todo en desarrollo
else:
    origins = ["https://miapp.com"]  # Solo dominios específicos en producción

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Ejemplo: Timing Middleware

```python
# app/middleware/TimingMiddleware.py
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        process_time = time.time() - start_time

        # Agregar header con tiempo de procesamiento
        response.headers["X-Process-Time"] = str(process_time)

        return response
```

## Middlewares Útiles de Terceros

### GZip Compression

```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)  # Comprimir responses >1KB
```

### Trusted Host

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["miapp.com", "*.miapp.com"]
)
```

### HTTPS Redirect

```python
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

if APP_ENV == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
```

## Orden Completo de Middlewares

Ejemplo de configuración completa en orden de ejecución:

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.environments import APP_ENV, LOGGER_MIDDLEWARE_ENABLED
from app.middleware.ContextMiddleware import ContextMiddleware
from app.middleware.LoggerMiddleware import LoggerMiddleware
from app.middleware.RateLimitMiddleware import RateLimitMiddleware
from app.middleware.AuthMiddleware import AuthMiddleware

app = FastAPI()

# Orden de registro (inverso al de ejecución)
app.add_middleware(GZipMiddleware, minimum_size=1000)      # 6. Última (comprimir)
if LOGGER_MIDDLEWARE_ENABLED:
    app.add_middleware(LoggerMiddleware)                   # 5. Logging
app.add_middleware(AuthMiddleware)                         # 4. Autenticación
app.add_middleware(RateLimitMiddleware)                    # 3. Rate limiting
app.add_middleware(CORSMiddleware, allow_origins=["*"])    # 2. CORS
app.add_middleware(ContextMiddleware)                      # 1. Primera (Request ID)
```

**Flujo de ejecución:**

```
Request
  ↓
1. ContextMiddleware (genera Request ID)
  ↓
2. CORSMiddleware (valida origen)
  ↓
3. RateLimitMiddleware (verifica límites)
  ↓
4. AuthMiddleware (autenticación)
  ↓
5. LoggerMiddleware (registra request)
  ↓
Router/Endpoint
  ↓
5. LoggerMiddleware (registra response)
  ↓
6. GZipMiddleware (comprime response)
  ↓
Response
```

## Mejores Prácticas

### 1. Orden Correcto

```python
# ✅ Correcto (ContextMiddleware primero)
app.add_middleware(LoggerMiddleware)
app.add_middleware(ContextMiddleware)

# ❌ Incorrecto (LoggerMiddleware no tendrá Request ID)
app.add_middleware(ContextMiddleware)
app.add_middleware(LoggerMiddleware)
```

### 2. Manejo de Errores

```python
class MyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Manejar error
            logger.error(f"Error en middleware: {str(e)}")
            raise
```

### 3. Performance

```python
# ✅ Correcto (operaciones ligeras)
class FastMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.start_time = time.time()
        response = await call_next(request)
        return response

# ❌ Incorrecto (operaciones pesadas)
class SlowMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # NO hacer queries a BD en middleware
        user_count = db.execute_query("SELECT COUNT(*) FROM users")
        response = await call_next(request)
        return response
```

### 4. Configuración por Entorno

```python
from app.core.environments import APP_ENV

# Solo en desarrollo
if APP_ENV == "development":
    app.add_middleware(DebugMiddleware)

# Solo en producción
if APP_ENV == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
```

## Testing Middlewares

```python
# tests/test_middlewares.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_request_id_header():
    response = client.get("/")

    # Verificar que X-Request-ID está presente
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) == 16

def test_rate_limit():
    # Hacer 61 requests
    for i in range(61):
        response = client.get("/")

    # El request 61 debería ser rechazado
    assert response.status_code == 429
    assert "Rate limit" in response.json()["detail"]["msg"]
```

## Debugging

### Ver Middlewares Activos

```python
# En un endpoint de debug
@router.get("/debug/middlewares")
async def debug_middlewares():
    return {
        "middlewares": [
            type(m).__name__ for m in app.user_middleware
        ]
    }
```

### Logging de Middlewares

```python
class DebugMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.debug(f"Middleware ejecutándose: {self.__class__.__name__}")
        logger.debug(f"Request: {request.method} {request.url.path}")

        response = await call_next(request)

        logger.debug(f"Response: {response.status_code}")
        return response
```

## Recursos

- [FastAPI Middleware Documentation](https://fastapi.tiangolo.com/tutorial/middleware/)
- [Starlette Middleware](https://www.starlette.io/middleware/)
- [Context Management](context.md)
- [Sistema de Logging](logging.md)

---

**Siguiente**: [Mejores Prácticas](../development/best-practices.md)
