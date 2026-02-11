"""
Base SQLAlchemy para modelos ORM.

Define la clase base declarativa y mixins reutilizables para todos los modelos.
Establece naming conventions para constraints y provee funcionalidad común.
"""

from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming convention para constraints
# Esto asegura que Alembic genere nombres consistentes y descriptivos
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    Base declarativa para todos los modelos ORM.

    Todos los modelos deben heredar de esta clase para ser detectados
    por Alembic y poder usar el sistema de migraciones.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """
    Mixin que agrega campos de timestamp automáticos a los modelos.

    Campos:
        created_at: Timestamp de creación (automático)
        updated_at: Timestamp de última actualización (automático en updates)

    Uso:
        class MyModel(Base, TimestampMixin):
            __tablename__ = "my_table"
            id: Mapped[int] = mapped_column(primary_key=True)
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
        comment="Fecha y hora de creación del registro",
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Fecha y hora de última actualización del registro",
    )
