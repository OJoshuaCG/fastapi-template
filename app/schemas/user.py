from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.encoding import EncodedIdOut

_TEXT_MAX = 65_535  # columna TEXT de MariaDB


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=_TEXT_MAX)


class UserUpdate(BaseModel):
    """PATCH: solo los campos enviados se actualizan (model_dump(exclude_unset=True))."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=_TEXT_MAX)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _not_null_columns(self) -> Self:
        # Omitir el campo = no cambiarlo; enviar null en una columna NOT NULL es inválido (422)
        for field in ("email", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} no puede ser null")
        return self


class UserOut(BaseModel):
    id: EncodedIdOut  # int en Python, string ofuscado en el JSON
    username: str
    email: str
    full_name: str | None
    notes: str | None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
