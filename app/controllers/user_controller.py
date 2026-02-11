"""
User Controller - Lógica de Negocio

Este controller maneja la lógica de negocio relacionada con usuarios.
Orquesta entre routes y models siguiendo el patrón MVC.

Patrón: Routes → Controllers → Models → Database
"""

from app.exceptions import AppHttpException
from app.models.user_model import UserModel


class UserController:
    """Controller para operaciones de usuarios"""

    def __init__(self):
        self.user_model = UserModel()

    def get_user(self, user_id: int) -> dict:
        """
        Obtener usuario por ID

        Args:
            user_id: ID del usuario

        Returns:
            dict: Datos del usuario

        Raises:
            AppHttpException: Si el usuario no existe (404)
        """
        user = self.user_model.find_by_id(user_id)

        if not user:
            raise AppHttpException(
                message="Usuario no encontrado",
                status_code=404,
                context={"user_id": user_id}
            )

        return user

    def get_user_by_username(self, username: str) -> dict:
        """
        Obtener usuario por username

        Args:
            username: Username del usuario

        Returns:
            dict: Datos del usuario

        Raises:
            AppHttpException: Si el usuario no existe (404)
        """
        user = self.user_model.find_by_username(username)

        if not user:
            raise AppHttpException(
                message="Usuario no encontrado",
                status_code=404,
                context={"username": username}
            )

        return user

    def list_users(self, is_active: bool | None = None) -> list[dict]:
        """
        Listar todos los usuarios con filtros opcionales

        Args:
            is_active: Filtrar por estado activo (opcional)

        Returns:
            list[dict]: Lista de usuarios
        """
        return self.user_model.find_all(is_active=is_active)

    def create_user(self, user_data: dict) -> dict:
        """
        Crear nuevo usuario con validaciones de negocio

        Args:
            user_data: Datos del usuario (username, email, hashed_password)

        Returns:
            dict: Usuario creado

        Raises:
            AppHttpException: Si el username ya existe (409)
            AppHttpException: Si el email ya existe (409)
        """
        # Validar username único
        existing_user = self.user_model.find_by_username(user_data["username"])
        if existing_user:
            raise AppHttpException(
                message="El username ya está en uso",
                status_code=409,
                context={"username": user_data["username"]}
            )

        # Validar email único
        existing_email = self.user_model.find_by_email(user_data.get("email"))
        if existing_email:
            raise AppHttpException(
                message="El email ya está en uso",
                status_code=409,
                context={"email": user_data.get("email")}
            )

        # Crear usuario
        user_id = self.user_model.create(user_data)

        # Retornar usuario creado
        return self.user_model.find_by_id(user_id)

    def update_user(self, user_id: int, user_data: dict) -> dict:
        """
        Actualizar usuario existente

        Args:
            user_id: ID del usuario
            user_data: Datos a actualizar

        Returns:
            dict: Usuario actualizado

        Raises:
            AppHttpException: Si el usuario no existe (404)
            AppHttpException: Si el email ya está en uso (409)
        """
        # Validar que el usuario existe
        user = self.get_user(user_id)

        # Si se actualiza email, validar que no esté en uso
        if "email" in user_data:
            existing_email = self.user_model.find_by_email(user_data["email"])
            if existing_email and existing_email["id"] != user_id:
                raise AppHttpException(
                    message="El email ya está en uso",
                    status_code=409,
                    context={"email": user_data["email"]}
                )

        # Actualizar usuario
        self.user_model.update(user_id, user_data)

        # Retornar usuario actualizado
        return self.user_model.find_by_id(user_id)

    def delete_user(self, user_id: int) -> None:
        """
        Eliminar usuario (soft delete - marcar como inactivo)

        Args:
            user_id: ID del usuario

        Raises:
            AppHttpException: Si el usuario no existe (404)
        """
        # Validar que el usuario existe
        self.get_user(user_id)

        # Marcar como inactivo (soft delete)
        self.user_model.update(user_id, {"is_active": False})

    def hard_delete_user(self, user_id: int) -> None:
        """
        Eliminar usuario permanentemente (hard delete)

        Args:
            user_id: ID del usuario

        Raises:
            AppHttpException: Si el usuario no existe (404)
        """
        # Validar que el usuario existe
        self.get_user(user_id)

        # Eliminar permanentemente
        self.user_model.delete(user_id)
