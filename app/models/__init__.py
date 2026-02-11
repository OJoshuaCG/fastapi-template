"""
Modelos ORM del proyecto.

IMPORTANTE: Todos los modelos deben ser importados aquí para que Alembic
los detecte durante la generación automática de migraciones (autogenerate).

Al crear un nuevo modelo:
1. Crear el archivo en app/models/
2. Heredar de Base y opcionalmente TimestampMixin
3. Importar el modelo aquí
4. Agregarlo a __all__

Ejemplo:
    from app.models.new_model import NewModel
    __all__ = [..., "NewModel"]
"""

from app.models.base import Base, TimestampMixin
from app.models.user import User

__all__ = ["Base", "TimestampMixin", "User"]
