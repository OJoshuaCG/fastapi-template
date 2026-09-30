"""
UserController: lógica de negocio de usuarios.

Recibe sus dependencias (UserModel) por constructor → se inyecta con Depends y se
reemplaza en tests con dependency_overrides.

Recibe schemas (no dicts armados por la route) y decide cómo persistirlos.

Patrón: Routes → Controllers → (Services) → Models → Database
"""

from typing import Annotated

from fastapi import Depends

from app.exceptions import AppHttpException
from app.models.user_model import UserModel, UserModelDep
from app.schemas.user import UserCreate, UserUpdate
from app.utils.pagination import PaginationParams
from app.utils.passwords import encrypt_password


class UserController:
    def __init__(self, users: UserModel):
        self.users = users

    async def get_user(self, user_id: int) -> dict:
        user = await self.users.find_by_id(user_id)
        if not user:
            raise AppHttpException(
                "Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found"
            )
        return user

    async def list_users(
        self, pagination: PaginationParams, *, is_active: bool | None = None
    ) -> tuple[list[dict], int]:
        # Dos consultas secuenciales: cada una toma y devuelve su conexión al pool.
        # No usar asyncio.gather sobre la misma conexión/transacción.
        items = await self.users.find_all(
            limit=pagination.size, offset=pagination.offset, is_active=is_active
        )
        total = await self.users.count(is_active=is_active)
        return items, total

    async def create_user(self, payload: UserCreate) -> dict:
        data = payload.model_dump(exclude={"password"})
        data["encrypted_password"] = encrypt_password(payload.password)
        # Sin "SELECT para ver si existe": eso tiene carrera (TOCTOU).
        # El índice UNIQUE decide y el 409 llega desde la capa de datos.
        try:
            user_id = await self.users.create(data)
        except AppHttpException as e:
            if e.reason == "duplicate":
                raise AppHttpException(
                    "El username o email ya está en uso", 409, code="user_conflict"
                ) from e
            raise
        return await self.get_user(user_id)

    async def update_user(self, user_id: int, payload: UserUpdate) -> dict:
        data = payload.model_dump(exclude_unset=True)  # PATCH: solo lo enviado
        try:
            matched = await self.users.update(user_id, data)
        except AppHttpException as e:
            if e.reason == "duplicate":
                raise AppHttpException("El email ya está en uso", 409, code="user_conflict") from e
            raise
        if not matched and data:
            raise AppHttpException(
                "Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found"
            )
        return await self.get_user(user_id)

    async def delete_user(self, user_id: int) -> None:
        """Hard delete."""
        if not await self.users.delete(user_id):
            raise AppHttpException(
                "Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found"
            )


def get_user_controller(users: UserModelDep) -> UserController:
    return UserController(users)


UserControllerDep = Annotated[UserController, Depends(get_user_controller)]
