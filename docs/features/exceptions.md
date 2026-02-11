# Manejo de Excepciones

El proyecto incluye un sistema robusto de manejo de excepciones con tracking automático de ubicación y contexto.

## Componentes

1. **`AppHttpException`**: Excepción personalizada con tracking automático
2. **Exception Handlers**: Manejadores globales para errores controlados y no controlados
3. **Logging**: Registro automático de errores (opcional)

## AppHttpException

Excepción personalizada que captura automáticamente dónde se lanzó el error.

### Características

- Hereda de `HTTPException` de FastAPI
- Captura automáticamente: archivo, función, línea y código
- Soporta contexto adicional para debugging
- Comportamiento diferente en desarrollo vs producción

### Uso Básico

```python
from app.exceptions import AppHttpException

@router.get("/users/{user_id}")
async def get_user(user_id: int):
    user = db.execute_query(
        "SELECT * FROM users WHERE id = :id",
        {"id": user_id},
        fetchone=True
    )

    if not user:
        raise AppHttpException(
            message="Usuario no encontrado",
            status_code=404
        )

    return user
```

**Respuesta en producción:**

```json
{
  "detail": {
    "msg": "Usuario no encontrado",
    "type": "AppHttpException"
  }
}
```

**Respuesta en desarrollo (APP_ENV=development):**

```json
{
  "detail": {
    "msg": "Usuario no encontrado",
    "type": "AppHttpException",
    "loc": {
      "file": "app/routes/users.py",
      "function": "get_user",
      "line": 15,
      "code": "raise AppHttpException(...)"
    }
  }
}
```

### Con Contexto

```python
raise AppHttpException(
    message="Error al procesar pago",
    status_code=500,
    context={
        "user_id": user_id,
        "amount": amount,
        "payment_method": "credit_card",
        "error_code": "PAYMENT_DECLINED"
    }
)
```

**Respuesta en desarrollo:**

```json
{
  "detail": {
    "msg": "Error al procesar pago",
    "type": "AppHttpException",
    "context": {
      "user_id": 123,
      "amount": 99.99,
      "payment_method": "credit_card",
      "error_code": "PAYMENT_DECLINED"
    },
    "loc": {
      "file": "app/routes/payments.py",
      "function": "process_payment",
      "line": 42,
      "code": "raise AppHttpException(...)"
    }
  }
}
```

## Exception Handlers

### app_exception_handler

Maneja excepciones `AppHttpException`.

**Comportamiento:**

- **Desarrollo**: Retorna `message`, `context` y `loc`
- **Producción**: Solo retorna `message` y `type`
- **Logging**: Si `LOGGER_EXCEPTIONS_ENABLED=True`, registra WARNING

**Configuración en main.py:**

```python
from app.exceptions import AppHttpException, app_exception_handler

app.add_exception_handler(AppHttpException, app_exception_handler)
```

### generic_exception_handler

Maneja excepciones no controladas (errores inesperados).

**Ejemplos:**
- `ZeroDivisionError`
- `KeyError`
- `ValueError`
- Cualquier excepción no capturada

**Comportamiento:**

- **Desarrollo**: Retorna tipo de error, mensaje y ubicación completa
- **Producción**: Retorna mensaje genérico "Error interno del servidor"
- **Logging**: Si `LOGGER_EXCEPTIONS_ENABLED=True`, registra ERROR

**Configuración en main.py:**

```python
from app.exceptions import generic_exception_handler

app.add_exception_handler(Exception, generic_exception_handler)
```

## Logging de Excepciones

### Configuración

```env
LOGGER_EXCEPTIONS_ENABLED=True
```

### AppHttpException (WARNING)

```python
raise AppHttpException(
    message="Usuario no encontrado",
    status_code=404,
    context={"user_id": 123}
)
```

**Log generado:**

```
2026-02-11 10:35:20 [WARNING] a1b2c3d4e5f6g7h8 | Exception: AppHttpException | Message: Usuario no encontrado | Status Code: 404 | Context: {'user_id': 123} | Loc: {'file': 'app/routes/users.py', 'function': 'get_user', 'line': 15, 'code': 'raise AppHttpException(...)'}
```

### Excepción No Controlada (ERROR)

```python
result = 10 / 0  # ZeroDivisionError
```

**Log generado:**

```
2026-02-11 10:36:00 [ERROR] a1b2c3d4e5f6g7h8 | Exception: ZeroDivisionError | Message: UNHANDLED EXC. "division by zero" | File: app/routes/users.py | Function: calculate_stats | Line: 78 | Code: "result = 10 / 0"
```

## Patrones Comunes

### Validación de Entrada

```python
@router.post("/users")
async def create_user(user: UserCreate):
    # Validar username único
    existing = db.execute_query(
        "SELECT id FROM users WHERE username = :username",
        {"username": user.username},
        fetchone=True
    )

    if existing:
        raise AppHttpException(
            message="El username ya existe",
            status_code=409,  # Conflict
            context={"username": user.username}
        )

    # Crear usuario
    # ...
```

### Autorización

```python
from app.core.context import current_user_id

@router.delete("/posts/{post_id}")
async def delete_post(post_id: int):
    current_user = current_user_id.get()

    if not current_user:
        raise AppHttpException(
            message="No autenticado",
            status_code=401
        )

    # Verificar que el post pertenece al usuario
    post = db.execute_query(
        "SELECT author_id FROM posts WHERE id = :id",
        {"id": post_id},
        fetchone=True
    )

    if not post:
        raise AppHttpException(
            message="Post no encontrado",
            status_code=404,
            context={"post_id": post_id}
        )

    if post["author_id"] != current_user:
        raise AppHttpException(
            message="No tienes permisos para eliminar este post",
            status_code=403,
            context={
                "post_id": post_id,
                "post_author": post["author_id"],
                "current_user": current_user
            }
        )

    # Eliminar post
    # ...
```

### Manejo de Errores de Base de Datos

```python
from app.exceptions import AppHttpException

@router.post("/users")
async def create_user(user: UserCreate):
    try:
        user_id = db.execute_query(
            "INSERT INTO users (username, email) VALUES (:username, :email)",
            {"username": user.username, "email": user.email}
        )
        return {"id": user_id}

    except Exception as e:
        logger.error(f"Error al crear usuario: {str(e)}")

        # Revisar si es error de duplicado (MySQL error 1062)
        if "Duplicate entry" in str(e):
            raise AppHttpException(
                message="El username o email ya existe",
                status_code=409,
                context={"username": user.username, "email": user.email}
            )

        # Error genérico
        raise AppHttpException(
            message="Error al crear usuario",
            status_code=500,
            context={"error": str(e)}
        )
```

### API Externa

```python
import httpx
from app.exceptions import AppHttpException

@router.get("/external-data")
async def get_external_data():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.example.com/data")
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        raise AppHttpException(
            message="Error al consumir API externa",
            status_code=502,  # Bad Gateway
            context={
                "url": str(e.request.url),
                "status_code": e.response.status_code
            }
        )

    except httpx.RequestError as e:
        raise AppHttpException(
            message="No se pudo conectar con API externa",
            status_code=503,  # Service Unavailable
            context={"error": str(e)}
        )
```

## Status Codes Comunes

| Code | Nombre                | Uso                                          |
|------|-----------------------|----------------------------------------------|
| 400  | Bad Request           | Parámetros inválidos                         |
| 401  | Unauthorized          | No autenticado (falta token)                 |
| 403  | Forbidden             | Autenticado pero sin permisos                |
| 404  | Not Found             | Recurso no existe                            |
| 409  | Conflict              | Conflicto (ej: username duplicado)           |
| 422  | Unprocessable Entity  | Validación de Pydantic falla                 |
| 429  | Too Many Requests     | Rate limit excedido                          |
| 500  | Internal Server Error | Error inesperado                             |
| 502  | Bad Gateway           | Error en servicio externo                    |
| 503  | Service Unavailable   | Servicio temporalmente no disponible         |

## Desarrollo vs Producción

### Variables de Entorno

```env
# Desarrollo
APP_ENV=development
LOGGER_EXCEPTIONS_ENABLED=True

# Producción
APP_ENV=production
LOGGER_EXCEPTIONS_ENABLED=True
```

### Respuestas en Desarrollo

```json
{
  "detail": {
    "msg": "Usuario no encontrado",
    "type": "AppHttpException",
    "context": {
      "user_id": 123
    },
    "loc": {
      "file": "app/routes/users.py",
      "function": "get_user",
      "line": 15,
      "code": "raise AppHttpException(...)"
    }
  }
}
```

### Respuestas en Producción

```json
{
  "detail": {
    "msg": "Usuario no encontrado",
    "type": "AppHttpException"
  }
}
```

**Nota**: `context` y `loc` se ocultan por seguridad.

## Mejores Prácticas

### 1. Mensajes Descriptivos

```python
# ✅ Correcto
raise AppHttpException(
    message="No se pudo procesar el pago: tarjeta rechazada",
    status_code=402
)

# ❌ Incorrecto
raise AppHttpException(
    message="Error",
    status_code=500
)
```

### 2. Usar Status Codes Apropiados

```python
# ✅ Correcto
raise AppHttpException(
    message="No autenticado",
    status_code=401
)

# ❌ Incorrecto
raise AppHttpException(
    message="No autenticado",
    status_code=500  # Debería ser 401
)
```

### 3. Incluir Contexto Útil

```python
# ✅ Correcto
raise AppHttpException(
    message="Usuario no encontrado",
    status_code=404,
    context={"user_id": user_id}  # Ayuda a debugging
)

# ❌ Incorrecto
raise AppHttpException(
    message="Usuario no encontrado",
    status_code=404
)
```

### 4. No Exponer Información Sensible

```python
# ❌ NUNCA hacer esto
raise AppHttpException(
    message=f"Error de autenticación",
    context={"password": password}  # NUNCA exponer passwords
)

# ✅ Correcto
raise AppHttpException(
    message="Credenciales inválidas",
    status_code=401
)
```

### 5. Catch Specific Exceptions

```python
# ✅ Correcto
try:
    # ...
except ValueError as e:
    raise AppHttpException(
        message="Valor inválido",
        status_code=400,
        context={"error": str(e)}
    )
except Exception as e:
    raise AppHttpException(
        message="Error inesperado",
        status_code=500
    )

# ❌ Incorrecto
try:
    # ...
except Exception as e:
    raise  # Genérico, menos control
```

## Testing

### Test de Excepciones

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_user_not_found():
    response = client.get("/users/999999")

    assert response.status_code == 404
    assert response.json()["detail"]["msg"] == "Usuario no encontrado"

def test_unauthorized():
    response = client.get("/profile")  # Requiere auth

    assert response.status_code == 401
```

## Recursos

- [FastAPI Exception Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [Sistema de Logging](logging.md)

---

**Siguiente**: [Middlewares](middlewares.md)
