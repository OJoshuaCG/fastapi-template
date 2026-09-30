"""
UserModel: acceso a la tabla `users` con SQL directo (async).

Patrón: Routes → Controllers → Models → Database
"""

from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.database import Database, DatabaseDep

# Nunca seleccionar encrypted_password en consultas que terminan en una respuesta
_PUBLIC_COLUMNS = (
    "id, username, email, full_name, notes, is_active, is_superuser, created_at, updated_at"
)
_INSERT_COLUMNS = (
    "username",
    "email",
    "encrypted_password",
    "full_name",
    "notes",
    "is_active",
    "is_superuser",
)
# Whitelist: los nombres de columna se interpolan en el SQL, NUNCA aceptar claves arbitrarias
_UPDATABLE_COLUMNS = frozenset(
    {"email", "full_name", "notes", "is_active", "is_superuser", "encrypted_password"}
)


class UserModel:
    def __init__(self, db: Database):
        self.db = db

    async def find_by_id(self, user_id: int, *, conn: AsyncConnection | None = None) -> dict | None:
        return await self.db.fetch_one(
            f"SELECT {_PUBLIC_COLUMNS} FROM users WHERE id = :id",  # noqa: S608 — columnas constantes
            {"id": user_id},
            conn=conn,
        )

    async def find_all(
        self, *, limit: int, offset: int, is_active: bool | None = None
    ) -> list[dict]:
        where, params = self._filters(is_active)
        return await self.db.fetch_all(
            f"SELECT {_PUBLIC_COLUMNS} FROM users {where} "  # noqa: S608
            "ORDER BY id DESC LIMIT :limit OFFSET :offset",
            {**params, "limit": limit, "offset": offset},
        )

    async def count(self, *, is_active: bool | None = None) -> int:
        where, params = self._filters(is_active)
        return int(await self.db.fetch_value(f"SELECT COUNT(*) FROM users {where}", params) or 0)  # noqa: S608

    async def create(self, data: dict[str, Any], *, conn: AsyncConnection | None = None) -> int:
        """Inserta y retorna el id. Un username/email duplicado lanza 409 (lo decide el UNIQUE)."""
        params = {col: data.get(col) for col in _INSERT_COLUMNS}
        result = await self.db.execute(
            """
            INSERT INTO users
                (username, email, encrypted_password, full_name, notes, is_active, is_superuser)
            VALUES (:username, :email, :encrypted_password, :full_name, :notes,
                    COALESCE(:is_active, 1), COALESCE(:is_superuser, 0))
            """,
            params,
            conn=conn,
        )
        return int(result.lastrowid or 0)

    async def update(
        self, user_id: int, data: dict[str, Any], *, conn: AsyncConnection | None = None
    ) -> int:
        """Actualiza solo columnas de la whitelist. Retorna filas encontradas."""
        unknown = set(data) - _UPDATABLE_COLUMNS
        if unknown:
            # Error de programación (el schema no debería permitirlo), no un error HTTP:
            # los models no conocen la capa HTTP
            raise ValueError(f"Columnas no actualizables: {sorted(unknown)}")
        if not data:
            return 0
        set_clause = ", ".join(f"{col} = :{col}" for col in data)  # col ∈ whitelist
        result = await self.db.execute(
            f"UPDATE users SET {set_clause} WHERE id = :id",  # noqa: S608
            {**data, "id": user_id},
            conn=conn,
        )
        return result.rowcount

    async def delete(self, user_id: int) -> int:
        result = await self.db.execute("DELETE FROM users WHERE id = :id", {"id": user_id})
        return result.rowcount

    @staticmethod
    def _filters(is_active: bool | None) -> tuple[str, dict[str, Any]]:
        if is_active is None:
            return "", {}
        return "WHERE is_active = :is_active", {"is_active": is_active}


def get_user_model(db: DatabaseDep) -> UserModel:
    return UserModel(db)


UserModelDep = Annotated[UserModel, Depends(get_user_model)]
