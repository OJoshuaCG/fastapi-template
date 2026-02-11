# Sistema de Logging

El proyecto incluye un sistema de logging centralizado y configurable que facilita el debugging y monitoreo de la aplicación.

## Arquitectura

El sistema de logging está compuesto por:

1. **`app/core/logger.py`**: Módulo central de logging
2. **`app/middleware/LoggerMiddleware.py`**: Middleware para logging automático de requests/responses
3. **Variables de entorno**: Configuración del comportamiento

## Configuración

### Variables de Entorno

En `.env`:

```env
# Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOGGER_LEVEL=INFO

# Habilitar middleware de logging
LOGGER_MIDDLEWARE_ENABLED=True

# Mostrar headers en logs (útil para debugging, desactivar en producción)
LOGGER_MIDDLEWARE_SHOW_HEADERS=False

# Habilitar logging de excepciones
LOGGER_EXCEPTIONS_ENABLED=True
```

### Niveles de Logging

| Nivel    | Uso                                       | Ejemplo                                      |
|----------|-------------------------------------------|----------------------------------------------|
| DEBUG    | Información detallada para debugging      | Valores de variables, estados internos       |
| INFO     | Confirmación de operaciones normales      | "Usuario creado", "Request procesado"        |
| WARNING  | Situación inusual pero manejable          | "Intento de login fallido", "Cache miss"     |
| ERROR    | Error que impide completar una operación  | "Error en BD", "API externa no responde"     |
| CRITICAL | Error crítico que puede detener la app    | "BD inaccesible", "Memoria agotada"          |

## Uso Básico

### Importar Logger

```python
from app.core.logger import get_logger

# Logger con nombre del módulo
logger = get_logger(__name__)

# Logger con nombre personalizado
logger = get_logger("my_custom_logger")

# Logger con nivel específico
logger = get_logger(__name__, level="DEBUG")
```

### Logging en Endpoints

```python
from fastapi import APIRouter
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.post("/users")
async def create_user(user: UserCreate):
    logger.info(f"Creando usuario: {user.username}")

    try:
        # Lógica de creación
        logger.debug(f"Datos del usuario: {user.dict()}")
        new_user = create_user_in_db(user)
        logger.info(f"Usuario creado exitosamente: ID {new_user.id}")
        return new_user
    except Exception as e:
        logger.error(f"Error al crear usuario: {str(e)}")
        raise
```

### Logging con Contexto

Usa el Request ID para correlacionar logs:

```python
from app.core.context import current_http_identifier
from app.core.logger import get_logger

logger = get_logger(__name__)

@router.get("/users/{user_id}")
async def get_user(user_id: int):
    request_id = current_http_identifier.get()
    logger.info(f"{request_id} | Obteniendo usuario ID {user_id}")

    # ...

    logger.info(f"{request_id} | Usuario encontrado: {user.username}")
    return user
```

## Logger Middleware

El `LoggerMiddleware` registra automáticamente todas las requests y responses.

### Funcionamiento

1. **Request**: Registra método, path, query params, body, headers (opcional)
2. **Response**: Registra status code, tiempo de procesamiento
3. **Request ID**: Usa el ID generado por `ContextMiddleware` para correlación

### Ejemplo de Logs

Con `LOGGER_MIDDLEWARE_ENABLED=True`:

```
2026-02-11 10:30:15 [INFO] a1b2c3d4e5f6g7h8 | Host: 127.0.0.1 | Request: POST /users | Body: {'username': 'john', 'email': 'john@example.com'} | Query: <no parameters>
2026-02-11 10:30:15 [INFO] a1b2c3d4e5f6g7h8 | Host: 127.0.0.1 | Response: POST /users | Status: 201 | Duration: 0.156s
```

### Ocultar Información Sensible

El middleware oculta automáticamente el body en rutas sensibles:

```python
# app/middleware/LoggerMiddleware.py
logger_info_request = [
    str(unique_id),
    f"Host: {client_ip}",
    f"Request: {method} {path}",
    f"Body: {'<cannot show>' if path in ['/user/login'] else body}",
    f"Query: {query_string if query_string else '<no parameters>'}",
]
```

**Personalizar rutas sensibles:**

```python
# Agregar más rutas a la lista
SENSITIVE_ROUTES = ['/user/login', '/auth/register', '/password/reset']

f"Body: {'<cannot show>' if path in SENSITIVE_ROUTES else body}",
```

### Mostrar Headers

Para debugging, puedes habilitar logging de headers:

```env
LOGGER_MIDDLEWARE_SHOW_HEADERS=True
```

**Advertencia**: Desactiva esto en producción para evitar logging de tokens de autenticación.

## Logging de Excepciones

### Configuración

```env
LOGGER_EXCEPTIONS_ENABLED=True
```

### Excepciones Controladas (AppHttpException)

```python
from app.exceptions import AppHttpException

raise AppHttpException(
    message="Usuario no encontrado",
    status_code=404,
    context={"user_id": user_id}
)
```

**Log generado (WARNING):**

```
2026-02-11 10:35:20 [WARNING] a1b2c3d4e5f6g7h8 | Exception: AppHttpException | Message: Usuario no encontrado | Status Code: 404 | Context: {'user_id': 123} | Loc: {'file': 'app/routes/users.py', 'function': 'get_user', 'line': 45, 'code': 'raise AppHttpException(...)'}
```

### Excepciones No Controladas

```python
# Error inesperado
result = 10 / 0  # ZeroDivisionError
```

**Log generado (ERROR):**

```
2026-02-11 10:36:00 [ERROR] a1b2c3d4e5f6g7h8 | Exception: ZeroDivisionError | Message: UNHANDLED EXC. "division by zero" | File: app/routes/users.py | Function: calculate_stats | Line: 78 | Code: "result = 10 / 0"
```

## Buenas Prácticas

### 1. Usar el Nivel Apropiado

```python
# ✅ Correcto
logger.info("Usuario creado exitosamente")
logger.warning("Intento de acceso no autorizado")
logger.error("Error en conexión a base de datos")

# ❌ Incorrecto
logger.info("Error crítico en la aplicación")  # Debería ser ERROR o CRITICAL
logger.error("Procesando request normal")      # Debería ser INFO o DEBUG
```

### 2. Incluir Contexto Útil

```python
# ✅ Correcto
logger.error(f"Error al obtener usuario ID {user_id}: {str(e)}")

# ❌ Incorrecto
logger.error("Error")  # No proporciona información útil
```

### 3. Usar Request ID para Correlación

```python
# ✅ Correcto
request_id = current_http_identifier.get()
logger.info(f"{request_id} | Procesando pago para usuario {user_id}")
logger.info(f"{request_id} | Pago completado: ${amount}")

# Ahora puedes buscar todos los logs de esta request con el Request ID
```

### 4. No Loggear Información Sensible

```python
# ❌ NUNCA hacer esto
logger.info(f"Usuario login: {username}, password: {password}")
logger.debug(f"Token: {auth_token}")

# ✅ Correcto
logger.info(f"Usuario login: {username}")
logger.debug("Token generado exitosamente")
```

### 5. Logging en Desarrollo vs Producción

```python
from app.core.environments import APP_ENV

if APP_ENV == "development":
    logger.debug(f"Query SQL: {query}")
    logger.debug(f"Parámetros: {params}")
else:
    # En producción, solo loggear información relevante
    logger.info("Query ejecutado exitosamente")
```

### 6. Usar f-strings para Performance

```python
# ✅ Mejor performance (f-string se evalúa solo si el nivel está activo)
logger.debug(f"Datos del usuario: {user.dict()}")

# ❌ Peor performance (string concatenation siempre se ejecuta)
logger.debug("Datos del usuario: " + str(user.dict()))
```

## Configuración Avanzada

### Logger Personalizado con Archivo

Si necesitas guardar logs en archivos:

```python
# app/core/logger.py
import logging
from logging.handlers import RotatingFileHandler

def get_logger(name=None, level=None, log_file=None):
    logger_name = name or APP_NAME
    logger_level = level or LOGGER_LEVEL

    logger = logging.getLogger(logger_name)
    logger.setLevel(logger_level)
    logger.propagate = False

    if not logger.hasHandlers():
        # Handler de consola
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Handler de archivo (opcional)
        if log_file:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10 MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger
```

Uso:

```python
logger = get_logger(__name__, log_file="app.log")
```

### Integración con Servicios Externos

#### Sentry (Recomendado para producción)

```bash
uv add sentry-sdk[fastapi]
```

```python
# main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from app.core.environments import APP_ENV

if APP_ENV == "production":
    sentry_sdk.init(
        dsn="your-sentry-dsn",
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
    )
```

#### LogRocket, Datadog, etc.

Similar al ejemplo de Sentry, sigue la documentación de cada servicio.

## Debugging con Logs

### Ver Logs en Tiempo Real

```bash
# Ejecutar aplicación y ver logs
uv run uvicorn main:app --reload

# Filtrar por nivel
uv run uvicorn main:app --reload | grep ERROR

# Buscar por Request ID
uv run uvicorn main:app --reload | grep a1b2c3d4e5f6g7h8
```

### Buscar Logs de una Request Específica

1. Cliente recibe error con `X-Request-ID` header
2. Buscar en logs por ese Request ID
3. Ver toda la cadena de logs de esa request

```bash
# Buscar todos los logs de un Request ID
cat app.log | grep a1b2c3d4e5f6g7h8
```

## Solución de Problemas

### Logs Duplicados

**Problema**: Cada log aparece dos veces.

**Causa**: `logger.propagate = True` (comportamiento por defecto de Python).

**Solución**: Ya implementado en `get_logger()`:

```python
logger.propagate = False  # Evita duplicación
```

### Logs No Aparecen

**Problema**: No se ven logs en consola.

**Causa**: Nivel de logging muy alto.

**Solución**:

```env
# Cambiar en .env
LOGGER_LEVEL=DEBUG  # Muestra todos los logs
```

### Demasiados Logs

**Problema**: Logs saturan la consola.

**Solución**:

```env
# Producción
LOGGER_LEVEL=WARNING
LOGGER_MIDDLEWARE_ENABLED=False  # Desactivar logging automático de requests
```

## Ejemplos Completos

### Endpoint con Logging Completo

```python
from fastapi import APIRouter, HTTPException
from app.core.logger import get_logger
from app.core.context import current_http_identifier
from app.exceptions import AppHttpException

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)

@router.get("/{user_id}")
async def get_user(user_id: int):
    request_id = current_http_identifier.get()

    logger.info(f"{request_id} | Obteniendo usuario ID {user_id}")

    try:
        # Buscar usuario en BD
        logger.debug(f"{request_id} | Ejecutando query para usuario {user_id}")
        user = db.execute_query(
            "SELECT * FROM users WHERE id = :id",
            {"id": user_id},
            fetchone=True
        )

        if not user:
            logger.warning(f"{request_id} | Usuario {user_id} no encontrado")
            raise AppHttpException(
                message="Usuario no encontrado",
                status_code=404,
                context={"user_id": user_id}
            )

        logger.info(f"{request_id} | Usuario encontrado: {user['username']}")
        return user

    except AppHttpException:
        raise
    except Exception as e:
        logger.error(f"{request_id} | Error inesperado al obtener usuario: {str(e)}")
        raise AppHttpException(
            message="Error interno del servidor",
            status_code=500,
            context={"error": str(e)}
        )
```

## Recursos

- [Documentación de logging de Python](https://docs.python.org/3/library/logging.html)
- [Context Management](context.md) - Para usar Request ID
- [Manejo de Excepciones](exceptions.md) - Para logging de errores
- [Middlewares](middlewares.md) - LoggerMiddleware

---

**Siguiente**: [Context Management](context.md)
