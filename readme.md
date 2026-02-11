# Comenzar desde 0

Iniciamos `uv`

```
uv init
```

Instalamos FastAPI
```
uv add fastapi[standard]
```

Ejecutamos FastAPI, para acceder a la aplicacion nos dirigimos a [localhost:8000/docs](http://localhost:8000/docs)

```
uv run uvicorn main:app --reload
```

Si lo deseamos, podemos especificar el puerto y permitir el acceso a cualquier host.
Por ejemplo, el siguiente comando nos permitira acceder a traves de [localhost:8080/docs](http://localhost:8080/docs)

```
uv run uvicorn main:app --reload --port 80 --host 0.0.0.0
```

## Migraciones de Base de Datos

Este proyecto utiliza **Alembic** para gestionar las migraciones de base de datos de forma automática y versionada.

### Comandos Rápidos

```bash
# Crear migración automática (detecta cambios en modelos)
uv run alembic revision --autogenerate -m "descripción de los cambios"

# Aplicar todas las migraciones pendientes
uv run alembic upgrade head

# Revertir última migración
uv run alembic downgrade -1

# Ver estado actual
uv run alembic current

# Ver historial de migraciones
uv run alembic history
```

### Crear un Nuevo Modelo

1. Crear modelo en `app/models/`:
   ```python
   # app/models/post.py
   from sqlalchemy import String
   from sqlalchemy.orm import Mapped, mapped_column
   from app.models.base import Base, TimestampMixin

   class Post(Base, TimestampMixin):
       __tablename__ = "posts"
       id: Mapped[int] = mapped_column(primary_key=True)
       title: Mapped[str] = mapped_column(String(200))
   ```

2. **Importar en `app/models/__init__.py`** (¡Crítico!):
   ```python
   from app.models.post import Post
   __all__ = [..., "Post"]
   ```

3. Generar y aplicar migración:
   ```bash
   uv run alembic revision --autogenerate -m "add posts table"
   uv run alembic upgrade head
   ```

### Documentación Completa

Ver [README_MIGRATIONS.md](README_MIGRATIONS.md) para:
- Workflow detallado de migraciones
- Mejores prácticas
- Troubleshooting
- Integración con SQL directo
- Comandos avanzados
