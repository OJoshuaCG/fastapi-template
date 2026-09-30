# Formato de Respuestas

Las respuestas exitosas usan el envelope `ApiResponse[T]` (`app/utils/response.py`). Los errores usan otro formato (`{"detail": {...}}`), que generan los exception handlers. Ver [Manejo de Excepciones](exceptions.md).

## `ApiResponse[T]`

```python
class ApiResponse[T](BaseModel):
    data: T | None = Field(default=None, exclude_if=_is_none)
    message: str | None = Field(default=None, exclude_if=_is_none)
    pagination: PaginationMeta | None = Field(default=None, exclude_if=_is_none)
```

Solo los campos de **primer nivel** con valor `None` se excluyen del JSON (`Field(exclude_if=...)`). No hace falta `response_model_exclude_none=True`. Los `None` **dentro** de `data` se conservan (ej. `"full_name": null`). El esquema OpenAPI conserva `data`, `message` y `pagination` tipados, así que los clientes generados tienen tipos.

## Helpers

| Helper | Uso | Salida |
|---|---|---|
| `success(data=..., message=None)` | GET/POST/PATCH con datos | `{"data": {...}}` / `{"data": {...}, "message": "..."}` |
| `paginated(items, total=..., pagination=..., message=None)` | listas paginadas | `{"data": [...], "pagination": {...}}` |
| `empty(message=None)` | DELETE, acciones void | `{"message": "..."}` / `{}` |

## Ejemplos

```python
from fastapi import status

from app.controllers.user_controller import UserControllerDep
from app.schemas.user import UserCreate, UserOut
from app.utils.pagination import PaginationDep
from app.utils.response import ApiResponse, empty, paginated, success


@router.get("/{user_id}", response_model=ApiResponse[UserOut])
async def get_user(user_id: int, users: UserControllerDep):
    return success(data=await users.get_user(user_id))


@router.post("", response_model=ApiResponse[UserOut], status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, users: UserControllerDep):
    ...
    return success(data=created, message="Usuario creado exitosamente")


@router.get("", response_model=ApiResponse[list[UserOut]])
async def list_users(pagination: PaginationDep, users: UserControllerDep):
    items, total = await users.list_users(pagination)
    return paginated(items, total=total, pagination=pagination)


@router.delete("/{user_id}", response_model=ApiResponse[None])
async def delete_user(user_id: int, users: UserControllerDep):
    await users.delete_user(user_id)
    return empty("Usuario eliminado exitosamente")
```

## `response_model` como filtro

Declara siempre `response_model=ApiResponse[TuSchemaOut]`. Además de documentar en OpenAPI, FastAPI **filtra** la salida al schema: si el dict del model trae columnas extra, no llegan al cliente.

Aun así, no selecciones columnas sensibles en consultas que terminan en una respuesta. `UserModel` usa `_PUBLIC_COLUMNS` y nunca devuelve `encrypted_password`.

## Cuándo no usar el envelope

- `/health` y `/ready` responden JSON plano (`{"status": "ok", ...}`), que es lo que esperan los orquestadores.
- `StreamingResponse`, `FileResponse` o redirecciones se devuelven directamente (ver `GET /api/v1/test/stream`).

Fuera de esos casos:

```python
# ✅
return success(data=user)

# ❌ Rompe el formato estándar
return {"id": 1, "name": "John"}
```

---

Ver también: [Paginación](pagination.md) · [Manejo de Excepciones](exceptions.md)
