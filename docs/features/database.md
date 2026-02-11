# Base de Datos

El proyecto soporta dos enfoques para interactuar con la base de datos: **SQL directo** y **ORM (SQLAlchemy)**. Ambos pueden coexistir en el mismo proyecto.

## Configuración

### Variables de Entorno

```env
DB_HOST=localhost
DB_USER=tu_usuario
DB_PASS=tu_contraseña
DB_NAME=nombre_bd
DB_PORT=3306
DB_ENGINE=mysql
```

### Clase Database

La clase `Database` en `app/core/database.py` gestiona las conexiones:

```python
from app.core.database import Database
from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT, DB_ENGINE

db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_ENGINE)
```

**Características:**
- Pool de conexiones (size=10, max_overflow=20)
- Reconnect automático (pool_recycle=180s)
- Pre-ping (valida conexiones antes de usar)
- Charset utf8mb4 con collation utf8mb4_general_ci

## SQL Directo

### execute_query()

Método principal para ejecutar consultas SQL directamente.

#### SELECT (Múltiples Filas)

```python
users = db.execute_query(
    "SELECT * FROM users WHERE is_active = :active",
    {"active": True},
    fetchone=False  # Retorna lista de diccionarios
)

# users = [
#     {"id": 1, "username": "john", "email": "john@example.com"},
#     {"id": 2, "username": "jane", "email": "jane@example.com"}
# ]

for user in users:
    print(user["username"])
```

#### SELECT (Una Fila)

```python
user = db.execute_query(
    "SELECT * FROM users WHERE id = :id",
    {"id": 1},
    fetchone=True  # Retorna un diccionario o None
)

# user = {"id": 1, "username": "john", "email": "john@example.com"}
# o None si no existe

if user:
    print(user["username"])
```

#### INSERT

```python
# Retorna last inserted ID
user_id = db.execute_query(
    "INSERT INTO users (username, email, hashed_password) "
    "VALUES (:username, :email, :password)",
    {
        "username": "john",
        "email": "john@example.com",
        "password": "hashed_password_here"
    }
)

print(f"Usuario creado con ID: {user_id}")
```

#### UPDATE

```python
# Retorna número de filas afectadas
rows_affected = db.execute_query(
    "UPDATE users SET email = :email WHERE id = :id",
    {"email": "newemail@example.com", "id": 1}
)

print(f"Filas actualizadas: {rows_affected}")
```

#### DELETE

```python
# Retorna número de filas eliminadas
rows_deleted = db.execute_query(
    "DELETE FROM users WHERE id = :id",
    {"id": 1}
)

print(f"Filas eliminadas: {rows_deleted}")
```

### call_procedure()

Ejecuta stored procedures de MySQL.

```python
# Procedure sin parámetros
results = db.call_procedure("get_all_users")

# Procedure con parámetros
results = db.call_procedure("get_user_by_id", [1])

# Procedure con múltiples result sets
results = db.call_procedure("get_user_with_posts", [1])
# results = [
#     [{"id": 1, "username": "john"}],  # Primer result set (usuario)
#     [{"id": 1, "title": "Post 1"}]    # Segundo result set (posts)
# ]
```

## ORM (SQLAlchemy)

### Crear Modelo

```python
# app/models/post.py
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Post(Base, TimestampMixin):
    __tablename__ = "posts"
    __table_args__ = {"comment": "Tabla de posts del blog"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Relación
    author = relationship("User", back_populates="posts")
```

**IMPORTANTE**: Importar en `app/models/__init__.py`:

```python
from app.models.post import Post
__all__ = [..., "Post"]
```

### Migración

```bash
# Generar migración automática
uv run alembic revision --autogenerate -m "add posts table"

# Revisar archivo generado en alembic/versions/

# Aplicar migración
uv run alembic upgrade head
```

Ver [README_MIGRATIONS.md](../../README_MIGRATIONS.md) para guía completa.

### Consultas ORM

```python
from app.models import User, Post
from app.core.database import Database
from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT

db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)
session = db.get_declarative_base_session()

try:
    # SELECT
    user = session.query(User).filter(User.username == "john").first()

    # SELECT con múltiples condiciones
    users = session.query(User).filter(
        User.is_active == True,
        User.email.like("%@example.com")
    ).all()

    # SELECT con JOIN
    posts_with_authors = session.query(Post).join(User).filter(
        User.username == "john"
    ).all()

    # INSERT
    new_user = User(
        username="jane",
        email="jane@example.com",
        hashed_password="...",
        is_active=True
    )
    session.add(new_user)
    session.commit()

    # UPDATE
    user = session.query(User).filter(User.id == 1).first()
    user.email = "newemail@example.com"
    session.commit()

    # DELETE
    user = session.query(User).filter(User.id == 1).first()
    session.delete(user)
    session.commit()

finally:
    session.close()
```

## SQL Directo vs ORM

### Cuándo Usar SQL Directo

✅ **Ventajas:**
- Consultas complejas con múltiples JOINs
- Stored procedures existentes
- Optimización manual de queries
- Queries específicas de MySQL (MATCH AGAINST, etc.)
- Mayor control y flexibilidad

**Ejemplo:**

```python
# Query compleja con múltiples JOINs y agregaciones
stats = db.execute_query("""
    SELECT
        u.id,
        u.username,
        COUNT(DISTINCT p.id) as post_count,
        COUNT(DISTINCT c.id) as comment_count,
        AVG(p.views) as avg_views
    FROM users u
    LEFT JOIN posts p ON u.id = p.author_id
    LEFT JOIN comments c ON u.id = c.user_id
    WHERE u.created_at >= :date
    GROUP BY u.id
    ORDER BY post_count DESC
    LIMIT 10
""", {"date": "2024-01-01"}, fetchone=False)
```

### Cuándo Usar ORM

✅ **Ventajas:**
- CRUD simple
- Relaciones entre modelos
- Validación de tipos con Python
- Migraciones automáticas
- Code completion en IDE

**Ejemplo:**

```python
# CRUD simple con relaciones
user = session.query(User).filter(User.id == 1).first()

# Acceder a posts del usuario (relación)
for post in user.posts:
    print(post.title)
```

## Mejores Prácticas

### 1. Usar Parámetros (Prevenir SQL Injection)

```python
# ✅ Correcto (usa parámetros)
db.execute_query(
    "SELECT * FROM users WHERE id = :id",
    {"id": user_id}
)

# ❌ NUNCA hacer esto (vulnerable a SQL injection)
db.execute_query(f"SELECT * FROM users WHERE id = {user_id}")
```

### 2. Cerrar Sesiones ORM

```python
# ✅ Correcto (usa try/finally)
session = db.get_declarative_base_session()
try:
    user = session.query(User).first()
finally:
    session.close()

# ✅ También correcto (context manager personalizado)
with get_db_session() as session:
    user = session.query(User).first()
```

### 3. Commits en Transacciones

```python
# ✅ Correcto (commit después de múltiples operaciones)
try:
    user = User(username="john", email="john@example.com")
    session.add(user)

    post = Post(title="Primer post", author_id=user.id)
    session.add(post)

    session.commit()  # Un solo commit
except:
    session.rollback()
    raise
```

### 4. Manejo de Errores

```python
from app.exceptions import AppHttpException

try:
    user = db.execute_query(
        "SELECT * FROM users WHERE id = :id",
        {"id": user_id},
        fetchone=True
    )
except Exception as e:
    logger.error(f"Error al consultar usuario: {str(e)}")
    raise AppHttpException(
        message="Error en base de datos",
        status_code=500,
        context={"error": str(e)}
    )
```

## Patrones Comunes

### Repository Pattern

```python
# app/repositories/user_repository.py
from app.core.database import Database
from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT

class UserRepository:
    def __init__(self):
        self.db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)

    def find_by_id(self, user_id: int):
        return self.db.execute_query(
            "SELECT * FROM users WHERE id = :id",
            {"id": user_id},
            fetchone=True
        )

    def find_by_username(self, username: str):
        return self.db.execute_query(
            "SELECT * FROM users WHERE username = :username",
            {"username": username},
            fetchone=True
        )

    def create(self, user_data: dict):
        return self.db.execute_query(
            "INSERT INTO users (username, email, hashed_password) "
            "VALUES (:username, :email, :password)",
            user_data
        )

# Uso en endpoints
from app.repositories.user_repository import UserRepository

@router.get("/users/{user_id}")
async def get_user(user_id: int):
    repo = UserRepository()
    user = repo.find_by_id(user_id)
    if not user:
        raise AppHttpException("Usuario no encontrado", status_code=404)
    return user
```

### Paginación

```python
def paginate(query: str, params: dict, page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page

    # Contar total
    count_query = f"SELECT COUNT(*) as total FROM ({query}) as subquery"
    total = db.execute_query(count_query, params, fetchone=True)["total"]

    # Obtener datos paginados
    paginated_query = f"{query} LIMIT :limit OFFSET :offset"
    params.update({"limit": per_page, "offset": offset})
    data = db.execute_query(paginated_query, params, fetchone=False)

    return {
        "data": data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    }

# Uso
result = paginate(
    "SELECT * FROM users WHERE is_active = :active ORDER BY created_at DESC",
    {"active": True},
    page=1,
    per_page=20
)
```

## Troubleshooting

### Error: "Lost connection to MySQL server"

**Causa**: Conexión idle por mucho tiempo.

**Solución**: Ya configurado con `pool_recycle=180` y `pool_pre_ping=True`.

### Error: "Too many connections"

**Causa**: Pool de conexiones agotado.

**Solución**: Ajustar en `app/core/database.py`:

```python
self.engine = create_engine(DB_URL,
    pool_size=20,        # Aumentar
    max_overflow=40,     # Aumentar
    # ...
)
```

### Error: "Charset mismatch"

**Causa**: Tabla creada con charset diferente.

**Solución**:

```sql
ALTER TABLE users CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
```

## Recursos

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [README_MIGRATIONS.md](../../README_MIGRATIONS.md) - Guía de Alembic
- [Estructura del Proyecto](../project-structure.md)

---

**Siguiente**: [Manejo de Excepciones](exceptions.md)
