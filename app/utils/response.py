import math
from typing import Any

from pydantic import BaseModel, Field

from app.utils.pagination import PaginationParams


def _is_none(value: Any) -> bool:
    return value is None


class PaginationMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool


class ApiResponse[T](BaseModel):
    """
    Envelope estándar para todas las respuestas exitosas de la API.

    Campos:
        data:       Payload de la respuesta. Ausente en respuestas sin contenido.
        message:    Mensaje para el usuario final. Ausente si no se proporciona.
        pagination: Metadata de paginación. Solo presente en respuestas paginadas.

    Los campos de nivel superior con valor None se excluyen del JSON de salida
    (exclude_if), por lo que 'pagination' nunca aparece en respuestas no paginadas y
    'message' solo aparece cuando se proporciona. Los None DENTRO de 'data' se conservan.
    El esquema OpenAPI conserva los tres campos tipados (clientes generados con tipos).

    Nota sobre errores:
        Las excepciones (AppHttpException, RequestValidationError, etc.) retornan
        { "detail": {...} } a través de sus propios handlers. FastAPI no aplica
        response_model a las respuestas de exception handlers, por lo que no hay
        conflicto entre ambos formatos. Son capas independientes.

    Uso básico:
        @router.get("/{user_id}", response_model=ApiResponse[UserOut])
        async def get_user(user_id: int, users: UserControllerDep):
            return success(data=await users.get_user(user_id))

    Uso paginado:
        @router.get("", response_model=ApiResponse[list[UserOut]])
        async def list_users(pagination: PaginationDep, users: UserControllerDep):
            items, total = await users.list_users(pagination)
            return paginated(items, total=total, pagination=pagination)

    Uso sin contenido (DELETE, operaciones void):
        @router.delete("/{user_id}", response_model=ApiResponse[None])
        async def delete_user(user_id: int, users: UserControllerDep):
            await users.delete_user(user_id)
            return empty("Usuario eliminado exitosamente")
    """

    data: T | None = Field(default=None, exclude_if=_is_none)
    message: str | None = Field(default=None, exclude_if=_is_none)
    pagination: PaginationMeta | None = Field(default=None, exclude_if=_is_none)


# ---------------------------------------------------------------------------
# Helpers — retornan instancias de ApiResponse listas para usar en endpoints
# ---------------------------------------------------------------------------


def success(data: Any = None, message: str | None = None) -> ApiResponse:
    """
    Respuesta estándar exitosa con datos.

    Args:
        data:    Objeto, dict o lista a retornar como payload.
        message: Mensaje opcional para el usuario final.

    Ejemplo:
        return success(data=user)
        return success(data=user, message="Usuario creado exitosamente")

    Salida:
        {"data": {...}}
        {"data": {...}, "message": "Usuario creado exitosamente"}
    """
    return ApiResponse(data=data, message=message)


def paginated(
    data: list[Any],
    total: int,
    pagination: PaginationParams,
    message: str | None = None,
) -> ApiResponse:
    """
    Respuesta paginada estándar. 'data' y 'pagination' van al mismo nivel.

    Args:
        data:       Lista de elementos de la página actual.
        total:      Total de registros en BD (resultado de COUNT).
        pagination: Instancia de PaginationParams obtenida via Depends.
        message:    Mensaje opcional para el usuario final.

    Ejemplo:
        from app.utils.pagination import PaginationDep
        from app.utils.response import ApiResponse, paginated

        @router.get("/users", response_model=ApiResponse[list[UserOut]])
        async def list_users(pagination: PaginationDep, users: UserControllerDep):
            items, total = await users.list_users(pagination)
            return paginated(items, total=total, pagination=pagination)

    Salida:
        {
            "data": [...],
            "pagination": {
                "page": 1, "size": 20, "total": 150,
                "pages": 8, "has_next": true, "has_prev": false
            }
        }
    """
    pages = math.ceil(total / pagination.size) if total > 0 else 0

    return ApiResponse(
        data=data,
        message=message,
        pagination=PaginationMeta(
            page=pagination.page,
            size=pagination.size,
            total=total,
            pages=pages,
            has_next=pagination.page < pages,
            has_prev=pagination.page > 1,
        ),
    )


def empty(message: str | None = None) -> ApiResponse[None]:
    """
    Respuesta sin contenido de datos. Útil para DELETE o acciones void.

    'data' estará ausente. Solo incluye 'message' si se proporciona.

    Args:
        message: Mensaje opcional para el usuario final.

    Ejemplo:
        return empty("Usuario eliminado exitosamente")
        return empty()

    Salida:
        {"message": "Usuario eliminado exitosamente"}
        {}
    """
    return ApiResponse(data=None, message=message)
