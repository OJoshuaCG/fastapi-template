# Guía de Migraciones con Alembic

Este proyecto utiliza **Alembic** para gestionar las migraciones de base de datos de forma automática y versionada.

## Tabla de Contenidos

- [Configuración](#configuración)
- [Comandos Principales](#comandos-principales)
- [Workflow Típico](#workflow-típico)
- [Mejores Prácticas](#mejores-prácticas)
- [Troubleshooting](#troubleshooting)
- [Integración con el Proyecto](#integración-con-el-proyecto)

## Configuración

### Variables de Entorno

Alembic utiliza las mismas variables de entorno que el proyecto (definidas en `.env`):

```bash
DB_HOST=localhost
DB_USER=tu_usuario
DB_PASS=tu_contraseña
DB_NAME=nombre_bd
DB_PORT=3306
```

### Archivos Importantes

- `alembic/env.py`: Conecta Alembic con la aplicación, importa modelos y variables de entorno
- `alembic.ini`: Configuración principal de Alembic
- `app/models/__init__.py`: **CRÍTICO** - Todos los modelos deben importarse aquí
- `alembic/versions/`: Carpeta donde se guardan las migraciones

## Comandos Principales

### Ver Estado Actual

```bash
# Ver la revisión actual de la base de datos
uv run alembic current

# Ver historial de migraciones
uv run alembic history

# Ver historial con detalles
uv run alembic history --verbose
```

### Crear Migración

```bash
# Generar migración automáticamente (detecta cambios en modelos)
uv run alembic revision --autogenerate -m "descripción de los cambios"

# Crear migración manual (vacía)
uv run alembic revision -m "descripción"
```

### Aplicar Migraciones

```bash
# Aplicar todas las migraciones pendientes
uv run alembic upgrade head

# Aplicar siguiente migración
uv run alembic upgrade +1

# Aplicar hasta una revisión específica
uv run alembic upgrade <revision_id>

# Ver SQL sin ejecutar (dry run)
uv run alembic upgrade head --sql
```

### Revertir Migraciones

```bash
# Revertir última migración
uv run alembic downgrade -1

# Revertir todas las migraciones
uv run alembic downgrade base

# Revertir hasta una revisión específica
uv run alembic downgrade <revision_id>
```

## Workflow Típico

### 1. Crear o Modificar Modelo

Crea o modifica un modelo en `app/models/`:

```python
# app/models/post.py
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Relación
    author = relationship("User", back_populates="posts")
```

### 2. Importar en `app/models/__init__.py`

**¡CRÍTICO!** Sin este paso, Alembic no detectará el modelo:

```python
# app/models/__init__.py
from app.models.base import Base, TimestampMixin
from app.models.user import User
from app.models.post import Post  # AGREGAR

__all__ = ["Base", "TimestampMixin", "User", "Post"]  # AGREGAR
```

### 3. Generar Migración

```bash
uv run alembic revision --autogenerate -m "add posts table"
```

### 4. Revisar Migración Generada

Abre el archivo generado en `alembic/versions/` y verifica:

- ✅ Tablas correctas
- ✅ Columnas con tipos de datos apropiados
- ✅ Constraints (PK, FK, Unique)
- ✅ Índices
- ✅ Server defaults
- ✅ Función `downgrade()` correcta

**Ejemplo de revisión:**

```python
def upgrade() -> None:
    op.create_table('posts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], name='fk_posts_author_id_users'),
        sa.PrimaryKeyConstraint('id', name='pk_posts')
    )
```

### 5. Aplicar Migración

```bash
uv run alembic upgrade head
```

### 6. Verificar en la Base de Datos

```sql
SHOW TABLES;
DESCRIBE posts;
SELECT * FROM alembic_version;
```

## Mejores Prácticas

### ✅ DO - Hacer

- **Revisar siempre** las migraciones autogeneradas antes de aplicarlas
- **Probar migraciones** en desarrollo antes de producción
- **Usar mensajes descriptivos** al crear migraciones
  - ✅ `"add email verification to users"`
  - ❌ `"update users"`
- **Versionar migraciones** en Git (commit después de crear y revisar)
- **Importar todos los modelos** en `app/models/__init__.py`
- **Usar TimestampMixin** para campos `created_at` / `updated_at`
- **Probar downgrade** localmente antes de mergear
- **Un cambio lógico por migración** (facilita rollbacks)

### ❌ DON'T - No Hacer

- ❌ **NO editar migraciones ya aplicadas** en producción
- ❌ **NO borrar migraciones del historial**
- ❌ **NO usar `--autogenerate` ciegamente** (siempre revisar)
- ❌ **NO mezclar cambios de esquema con datos** en una migración
- ❌ **NO commitear migraciones sin probar**
- ❌ **NO modificar `alembic_version` manualmente** (usar `alembic stamp`)
- ❌ **NO saltarse migraciones** en producción

## Troubleshooting

### Error: "Can't locate revision"

**Problema:** Base de datos y migraciones desincronizadas.

**Solución:**

```bash
# Verificar estado actual
uv run alembic current

# Si está vacío o incorrecto, marcar revisión manualmente
uv run alembic stamp head
```

### Error: "Target database is not up to date"

**Problema:** Hay migraciones pendientes.

**Solución:**

```bash
# Ver migraciones pendientes
uv run alembic history

# Aplicar migraciones
uv run alembic upgrade head
```

### Autogenerate no detecta cambios

**Causas comunes:**

1. **Modelo no importado en `app/models/__init__.py`**
   ```python
   # Verificar que el modelo esté en __all__
   from app.models.my_model import MyModel
   __all__ = [..., "MyModel"]
   ```

2. **Cambios en columnas opcionales**
   ```python
   # Alembic puede no detectar cambios de nullable
   # Revisar migración y agregar manualmente si es necesario
   op.alter_column('users', 'full_name', nullable=True)
   ```

3. **Server defaults con sintaxis diferente**
   ```python
   # MySQL: func.now() vs CURRENT_TIMESTAMP
   # Revisar y ajustar manualmente
   ```

### Ver SQL sin ejecutar

```bash
# Útil para debugging y validación
uv run alembic upgrade head --sql > migration.sql
cat migration.sql
```

### Revertir migración con errores

```bash
# Si una migración falla a mitad de aplicación
uv run alembic downgrade -1

# Corregir migración o modelo
# Regenerar migración
uv run alembic revision --autogenerate -m "fix: corrected migration"
```

### Base de datos en estado desconocido

```bash
# Marcar estado actual manualmente
uv run alembic stamp <revision_id>

# O marcar como head
uv run alembic stamp head
```

## Integración con el Proyecto

### Compatibilidad con SQL Directo

Alembic coexiste con el sistema actual de SQL directo:

```python
from app.core.database import Database
from app.models import User

# SQL directo (existente) - sigue funcionando
with db.get_session() as session:
    result = db.execute_query("SELECT * FROM users WHERE id = :id", {"id": 1}, fetchone=True)

# ORM (nuevo) - opcional
session = db.get_declarative_base_session()
try:
    user = session.query(User).filter(User.id == 1).first()
    print(user.username, user.email)
finally:
    session.close()
```

### Variables de Entorno Compartidas

`alembic/env.py` importa directamente desde `app.core.environments`:

```python
from app.core.environments import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER
```

No se requiere configuración adicional en `.env`.

### Charset y Collation

Las migraciones usan la misma configuración que `Database`:

- Charset: `utf8mb4`
- Collation: `utf8mb4_general_ci`
- Server timezone: UTC

### Modelo de Ejemplo: User

El proyecto incluye un modelo `User` de ejemplo en `app/models/user.py`:

```bash
# Generar migración para el modelo User
uv run alembic revision --autogenerate -m "create users table"

# Aplicar migración
uv run alembic upgrade head
```

Esto creará la tabla `users` con:
- Campos: `id`, `username`, `email`, `hashed_password`, `full_name`, `notes`, `is_active`, `is_superuser`
- Timestamps: `created_at`, `updated_at` (automáticos)
- Constraints: Primary key, unique en `username` y `email`
- Índices: En `username` y `email`

## Estructura de Archivos de Migración

```
alembic/
├── versions/
│   ├── 20260211_1430_a1b2c3d4e5f6_create_users_table.py
│   ├── 20260212_0900_b2c3d4e5f6g7_add_posts_table.py
│   └── 20260213_1500_c3d4e5f6g7h8_add_email_verification.py
├── env.py
└── script.py.mako
```

Cada archivo de migración contiene:
- **revision**: ID único de la migración
- **down_revision**: Migración anterior (forma cadena)
- **upgrade()**: Función para aplicar cambios
- **downgrade()**: Función para revertir cambios

## Comandos Avanzados

### Ver diferencias entre revisiones

```bash
# Comparar dos revisiones
uv run alembic show <revision_id>
```

### Mergear ramas de migraciones

```bash
# Si dos desarrolladores crearon migraciones en paralelo
uv run alembic merge <rev1> <rev2> -m "merge migrations"
```

### Crear migración con dependencias

```bash
# Especificar dependencia de otra rama
uv run alembic revision -m "new feature" --depends-on <other_revision>
```

## Recursos

- [Documentación oficial de Alembic](https://alembic.sqlalchemy.org/)
- [Tutorial de Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)

---

**Nota:** Para más información sobre la estructura del proyecto, ver `README.md`.
