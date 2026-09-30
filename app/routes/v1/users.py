"""
Ejemplo CRUD completo: Routes → Controllers → Models → Database (todo async).

La route solo: valida (schemas, EncodedId), llama UN método del controller y envuelve la
respuesta. Nada de negocio aquí (ni cifrar contraseñas ni armar dicts para el model).
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.controllers.user_controller import UserControllerDep
from app.core.encoding import EncodedId
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.utils.pagination import PaginationDep
from app.utils.response import ApiResponse, empty, paginated, success

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=ApiResponse[list[UserOut]])
async def list_users(
    users: UserControllerDep,
    pagination: PaginationDep,
    is_active: Annotated[bool | None, Query(description="Filtrar por estado")] = None,
):
    items, total = await users.list_users(pagination, is_active=is_active)
    return paginated(items, total=total, pagination=pagination)


@router.get("/{user_id}", response_model=ApiResponse[UserOut])
async def get_user(user_id: EncodedId, users: UserControllerDep):
    return success(data=await users.get_user(user_id))


@router.post("", response_model=ApiResponse[UserOut], status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, users: UserControllerDep):
    created = await users.create_user(payload)
    return success(data=created, message="Usuario creado exitosamente")


@router.patch("/{user_id}", response_model=ApiResponse[UserOut])
async def update_user(user_id: EncodedId, payload: UserUpdate, users: UserControllerDep):
    updated = await users.update_user(user_id, payload)
    return success(data=updated, message="Usuario actualizado")


@router.delete("/{user_id}", response_model=ApiResponse[None])
async def delete_user(user_id: EncodedId, users: UserControllerDep):
    await users.delete_user(user_id)
    return empty("Usuario eliminado exitosamente")
