# Mejores Prácticas de Desarrollo

Esta guía proporciona patrones, convenciones y mejores prácticas para desarrollar con esta plantilla FastAPI.

## Estructura de Código

### Organización de Endpoints

```python
# ✅ Correcto - Un archivo por recurso
# app/routes/users.py
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/")
async def list_users():
    pass

@router.post("/")
async def create_user():
    pass

@router.get("/{user_id}")
async def get_user(user_id: int):
    pass

# ❌ Incorrecto - Todo en un archivo
# app/routes/routes.py con 50 endpoints
```

### Separación de Responsabilidades (Patrón MVC)

Este proyecto sigue un patrón **MVC sin Vista** (solo backend):

**Routes → Controllers → Models → Database**

```python
# ✅ Correcto - Patrón MVC
# app/controllers/user_controller.py
from app.models.user_model import UserModel
from app.exceptions import AppHttpException

class UserController:
    def __init__(self):
        self.user_model = UserModel()

    def create_user(self, user_data: dict):
        # Lógica de negocio / validación
        existing = self.user_model.find_by_username(user_data["username"])
        if existing:
            raise AppHttpException("Username ya existe", 409)

        # Crear usuario a través del modelo
        user_id = self.user_model.create(user_data)
        return self.user_model.find_by_id(user_id)

    def get_user(self, user_id: int):
        user = self.user_model.find_by_id(user_id)
        if not user:
            raise AppHttpException("Usuario no encontrado", 404)
        return user

# app/routes/users.py
from app.controllers.user_controller import UserController

@router.post("/")
async def create_user(user: UserCreate):
    controller = UserController()
    return controller.create_user(user.dict())

@router.get("/{user_id}")
async def get_user(user_id: int):
    controller = UserController()
    return controller.get_user(user_id)

# ❌ Incorrecto - Lógica de negocio en endpoint
@router.post("/")
async def create_user(user: UserCreate):
    # 50 líneas de lógica de negocio aquí
    pass
```

### Model Pattern (Interacción con BD)

```python
# app/models/user_model.py
from app.core.database import Database
from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT

class UserModel:
    def __init__(self):
        self.db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)

    def find_by_id(self, user_id: int):
        """Buscar usuario por ID"""
        return self.db.execute_query(
            "SELECT * FROM users WHERE id = :id",
            {"id": user_id},
            fetchone=True
        )

    def find_by_username(self, username: str):
        """Buscar usuario por username"""
        return self.db.execute_query(
            "SELECT * FROM users WHERE username = :username",
            {"username": username},
            fetchone=True
        )

    def create(self, user_data: dict):
        """Crear nuevo usuario"""
        return self.db.execute_query(
            "INSERT INTO users (username, email, hashed_password) "
            "VALUES (:username, :email, :password)",
            user_data
        )

    def update(self, user_id: int, user_data: dict):
        """Actualizar usuario"""
        return self.db.execute_query(
            "UPDATE users SET email = :email WHERE id = :id",
            {"id": user_id, **user_data}
        )

    def delete(self, user_id: int):
        """Eliminar usuario"""
        return self.db.execute_query(
            "DELETE FROM users WHERE id = :id",
            {"id": user_id}
        )
```

## Validación de Datos

### Usar Pydantic Models

```python
# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

    class Config:
        from_attributes = True  # Para ORM models

# app/routes/users.py
@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate):
    # user ya está validado por Pydantic
    # password tiene min 8 caracteres
    # email es válido
    # username tiene 3-50 caracteres
    pass
```

### Validación Personalizada

```python
from pydantic import BaseModel, validator

class UserCreate(BaseModel):
    username: str
    password: str
    password_confirm: str

    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError('Username debe ser alfanumérico')
        return v

    @validator('password_confirm')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords no coinciden')
        return v
```

## Manejo de Errores

### Siempre Usar AppHttpException

```python
# ✅ Correcto
from app.exceptions import AppHttpException

if not user:
    raise AppHttpException(
        message="Usuario no encontrado",
        status_code=404,
        context={"user_id": user_id}
    )

# ❌ Incorrecto
from fastapi import HTTPException
raise HTTPException(status_code=404, detail="Not found")
```

### Try-Except Específico

```python
# ✅ Correcto
try:
    result = int(value)
except ValueError:
    raise AppHttpException("Valor debe ser numérico", 400)
except Exception as e:
    logger.error(f"Error inesperado: {str(e)}")
    raise AppHttpException("Error interno", 500)

# ❌ Incorrecto
try:
    result = int(value)
except:
    raise AppHttpException("Error", 500)
```

## Logging

### Siempre Incluir Request ID

```python
from app.core.logger import get_logger
from app.core.context import current_http_identifier

logger = get_logger(__name__)

@router.post("/users")
async def create_user(user: UserCreate):
    request_id = current_http_identifier.get()
    logger.info(f"{request_id} | Creando usuario: {user.username}")
    # ...
    logger.info(f"{request_id} | Usuario creado: ID {user_id}")
```

### Niveles Apropiados

```python
# INFO - Operaciones normales
logger.info(f"{request_id} | Usuario autenticado: {username}")

# WARNING - Situaciones inusuales
logger.warning(f"{request_id} | Intento de login fallido: {username}")

# ERROR - Errores que impiden completar operación
logger.error(f"{request_id} | Error en pago: {str(e)}")

# DEBUG - Información detallada (solo desarrollo)
logger.debug(f"{request_id} | Query SQL: {query}")
```

## Base de Datos

### Usar Parámetros (SQL Injection)

```python
# ✅ Correcto
db.execute_query(
    "SELECT * FROM users WHERE id = :id",
    {"id": user_id}
)

# ❌ NUNCA hacer esto
db.execute_query(f"SELECT * FROM users WHERE id = {user_id}")
```

### Cerrar Sesiones ORM

```python
# ✅ Correcto
session = db.get_declarative_base_session()
try:
    user = session.query(User).first()
finally:
    session.close()

# ❌ Incorrecto
session = db.get_declarative_base_session()
user = session.query(User).first()
# Session nunca se cierra
```

### Transacciones

```python
# ✅ Correcto
try:
    user = User(...)
    session.add(user)

    post = Post(author_id=user.id, ...)
    session.add(post)

    session.commit()  # Un solo commit
except Exception as e:
    session.rollback()
    raise
finally:
    session.close()
```

## Seguridad

### No Hardcodear Secretos

```python
# ❌ NUNCA hacer esto
SECRET_KEY = "mi_clave_super_secreta"
API_KEY = "sk_live_123abc"

# ✅ Correcto
from app.core.environments import SECRET_KEY, API_KEY
```

### Hashear Passwords

```bash
uv add passlib[bcrypt]
```

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hashear
hashed = pwd_context.hash(plain_password)

# Verificar
is_valid = pwd_context.verify(plain_password, hashed)
```

### Validar Permisos

```python
from app.core.context import current_user_id

@router.delete("/posts/{post_id}")
async def delete_post(post_id: int):
    current_user = current_user_id.get()

    if not current_user:
        raise AppHttpException("No autenticado", 401)

    post = get_post(post_id)

    if post.author_id != current_user:
        raise AppHttpException("Sin permisos", 403)

    # Eliminar post
```

## Performance

### Evitar N+1 Queries

```python
# ❌ Incorrecto (N+1 queries)
posts = db.execute_query("SELECT * FROM posts", fetchone=False)
for post in posts:
    author = db.execute_query(
        "SELECT * FROM users WHERE id = :id",
        {"id": post["author_id"]},
        fetchone=True
    )
    post["author"] = author

# ✅ Correcto (1 query con JOIN)
posts = db.execute_query("""
    SELECT
        p.*,
        u.username as author_username,
        u.email as author_email
    FROM posts p
    JOIN users u ON p.author_id = u.id
""", fetchone=False)
```

### Paginación

```python
@router.get("/users")
async def list_users(page: int = 1, per_page: int = 20):
    offset = (page - 1) * per_page

    users = db.execute_query(
        "SELECT * FROM users LIMIT :limit OFFSET :offset",
        {"limit": per_page, "offset": offset},
        fetchone=False
    )

    return {
        "data": users,
        "page": page,
        "per_page": per_page
    }
```

### Caché

```bash
uv add aiocache
```

```python
from aiocache import cached

@cached(ttl=300)  # Cache por 5 minutos
async def get_user_stats(user_id: int):
    return db.execute_query(
        "SELECT COUNT(*) as posts FROM posts WHERE author_id = :id",
        {"id": user_id},
        fetchone=True
    )
```

## Testing

### Instalar Dependencias de Testing

```bash
uv add --group dev pytest pytest-asyncio httpx
```

### Crear Tests

```python
# tests/test_users.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_user():
    response = client.post("/users", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123"
    })

    assert response.status_code == 201
    assert response.json()["username"] == "testuser"

def test_get_user_not_found():
    response = client.get("/users/999999")

    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]["msg"].lower()
```

### Ejecutar Tests

```bash
uv run pytest

# Con coverage
uv run pytest --cov=app --cov-report=html
```

## Git Workflow

### Commits Semánticos

```bash
# feat: Nueva funcionalidad
git commit -m "feat: agregar endpoint de autenticación"

# fix: Corrección de bug
git commit -m "fix: corregir validación de email"

# docs: Documentación
git commit -m "docs: actualizar README con ejemplos"

# refactor: Refactorización
git commit -m "refactor: extraer lógica de usuario a service"

# test: Tests
git commit -m "test: agregar tests de autenticación"

# chore: Mantenimiento
git commit -m "chore: actualizar dependencias"
```

### Branches

```bash
# Feature branch
git checkout -b feature/user-authentication

# Bugfix branch
git checkout -b fix/password-validation

# Hotfix branch (producción)
git checkout -b hotfix/critical-security-fix
```

## Variables de Entorno

### Desarrollo vs Producción

```env
# .env.development
APP_ENV=development
LOGGER_LEVEL=DEBUG
LOGGER_MIDDLEWARE_SHOW_HEADERS=True

# .env.production
APP_ENV=production
LOGGER_LEVEL=WARNING
LOGGER_MIDDLEWARE_SHOW_HEADERS=False
```

### Cargar según Entorno

```python
# config.py
import os
from dotenv import load_dotenv

env = os.getenv("ENV", "development")
load_dotenv(f".env.{env}")
```

## Documentación

### Docstrings

```python
def create_user(username: str, email: str) -> dict:
    """
    Crea un nuevo usuario en la base de datos.

    Args:
        username: Nombre de usuario único (3-50 caracteres)
        email: Email válido del usuario

    Returns:
        dict: Usuario creado con id, username, email

    Raises:
        AppHttpException: Si el username ya existe (409)
        AppHttpException: Si hay error en BD (500)

    Example:
        >>> user = create_user("john", "john@example.com")
        >>> print(user["id"])
        1
    """
    pass
```

### OpenAPI/Swagger

```python
@router.post(
    "/",
    response_model=UserResponse,
    status_code=201,
    summary="Crear usuario",
    description="Crea un nuevo usuario en el sistema",
    responses={
        201: {"description": "Usuario creado exitosamente"},
        409: {"description": "Username o email ya existe"},
        422: {"description": "Datos de entrada inválidos"}
    }
)
async def create_user(user: UserCreate):
    pass
```

## Monitoreo

### Health Check Endpoint

```python
@router.get("/health")
async def health_check():
    # Verificar BD
    try:
        db.execute_query("SELECT 1", fetchone=True)
        db_status = "ok"
    except:
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "version": "1.0.0"
    }
```

### Metrics Endpoint

```python
@router.get("/metrics")
async def metrics():
    return {
        "uptime": get_uptime(),
        "requests_total": request_counter,
        "requests_per_second": calculate_rps(),
        "db_connections": get_db_pool_size()
    }
```

## Recursos

- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Python Best Practices](https://docs.python-guide.org/)

---

**Siguiente**: [Despliegue](../deployment.md)
