# Estructura del Proyecto

Esta guía explica la organización de archivos y carpetas del proyecto, así como el propósito de cada componente.

## Vista General

```
fastapi-template/
├── app/                          # Código principal de la aplicación
│   ├── core/                     # Módulos centrales
│   ├── controllers/              # Controladores MVC (lógica de negocio)
│   ├── exceptions/               # Excepciones personalizadas
│   ├── middleware/               # Middlewares
│   ├── models/                   # Modelos de datos
│   │   ├── *.py                  # Modelos ORM SQLAlchemy (migraciones)
│   │   └── *_model.py            # Modelos de datos (SQL directo)
│   ├── routes/                   # Endpoints de la API
│   ├── schemas/                  # Schemas Pydantic (opcional)
│   └── utils/                    # Funciones utilitarias
├── alembic/                      # Sistema de migraciones
│   ├── versions/                 # Archivos de migración
│   ├── env.py                    # Configuración de Alembic
│   └── script.py.mako            # Template de migraciones
├── docs/                         # Documentación del proyecto
│   ├── features/                 # Docs de características
│   └── development/              # Docs de desarrollo
├── main.py                       # Punto de entrada FastAPI
├── pyproject.toml                # Dependencias y configuración
├── .pre-commit-config.yaml       # Configuración de pre-commit
├── .env.example                  # Template de variables de entorno
├── .env                          # Variables de entorno (no versionado)
├── .gitignore                    # Archivos ignorados por git
├── .secrets.baseline             # Baseline de detect-secrets
├── readme.md                     # Documentación principal
├── README_MIGRATIONS.md          # Guía de migraciones
└── CLAUDE.md                     # Guía para agentes de IA
```

## Patrón de Arquitectura: MVC (Sin Vista)

El proyecto sigue un patrón **MVC sin Vista** ya que es puro backend:

**Routes → Controllers → Models → Database**

- **Routes** (`app/routes/`): Definen endpoints y validan entrada (Pydantic schemas)
- **Controllers** (`app/controllers/`): Lógica de negocio, validaciones, orquestación
- **Models** (`app/models/`): Interacción con base de datos
  - `*.py` (ej: `user.py`): Modelos ORM SQLAlchemy para migraciones
  - `*_model.py` (ej: `user_model.py`): Modelos de datos con SQL directo

## Descripción de Carpetas

### `/app` - Código Principal

Contiene todo el código de la aplicación FastAPI siguiendo el patrón MVC.

#### `/app/core` - Módulos Centrales

**Propósito**: Configuración y utilidades fundamentales usadas en todo el proyecto.

```
app/core/
├── __init__.py
├── context.py          # ContextVars para estado de request
├── database.py         # Gestión de conexiones a base de datos
├── environments.py     # Variables de entorno centralizadas
└── logger.py           # Sistema de logging
```

**Archivos clave:**

- **`environments.py`**: Centraliza TODAS las variables de entorno
  - Variables de aplicación: `APP_ENV`, `APP_NAME`, `SECRET_KEY`
  - Variables de logging: `LOGGER_LEVEL`, `LOGGER_MIDDLEWARE_ENABLED`, etc.
  - Variables de base de datos: `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_PORT`
  - Usa `python-dotenv` para cargar desde `.env`

- **`logger.py`**: Sistema de logging centralizado
  - Función `get_logger(name, level)` para obtener loggers configurados
  - Evita duplicación de handlers
  - Formato consistente en toda la aplicación

- **`context.py`**: Mantiene estado de request con ContextVars
  - Similar a sesiones en PHP
  - Variables: `current_http_identifier`, `current_request_ip`, `current_user_id`, etc.
  - Establecidas automáticamente por `ContextMiddleware`

- **`database.py`**: Clase `Database` para interactuar con la BD
  - Soporta SQL directo (`execute_query()`)
  - Soporta Stored Procedures (`call_procedure()`)
  - Soporta ORM SQLAlchemy (`get_declarative_base_session()`)
  - Pool de conexiones configurado

#### `/app/controllers` - Controladores (MVC)

**Propósito**: Lógica de negocio, validaciones y orquestación entre routes y models.

```
app/controllers/
├── __init__.py
├── user_controller.py       # Controlador de usuarios
├── post_controller.py       # Controlador de posts
└── *_controller.py          # Otros controladores
```

**Patrón:**

```python
# app/controllers/user_controller.py
from app.models.user_model import UserModel
from app.exceptions import AppHttpException

class UserController:
    def __init__(self):
        self.user_model = UserModel()

    def get_user(self, user_id: int):
        """Obtener usuario por ID"""
        user = self.user_model.find_by_id(user_id)
        if not user:
            raise AppHttpException("Usuario no encontrado", 404)
        return user

    def create_user(self, user_data: dict):
        """Crear nuevo usuario con validaciones"""
        # Validar username único
        existing = self.user_model.find_by_username(user_data["username"])
        if existing:
            raise AppHttpException("Username ya existe", 409)

        # Crear usuario
        user_id = self.user_model.create(user_data)
        return self.user_model.find_by_id(user_id)

    def update_user(self, user_id: int, user_data: dict):
        """Actualizar usuario existente"""
        # Validar que existe
        user = self.get_user(user_id)

        # Actualizar
        self.user_model.update(user_id, user_data)
        return self.user_model.find_by_id(user_id)
```

**Responsabilidades:**
- Lógica de negocio (validaciones, cálculos)
- Orquestación entre múltiples modelos
- Manejo de errores con `AppHttpException`
- Transformación de datos si es necesario

#### `/app/exceptions` - Excepciones Personalizadas

**Propósito**: Manejo robusto de errores con tracking automático.

```
app/exceptions/
├── __init__.py
├── AppHttpException.py      # Excepción personalizada
└── HandlerExceptions.py     # Manejadores globales
```

**Características:**

- `AppHttpException`: Excepción que captura ubicación automáticamente
  - Archivo, función, línea y código donde se lanzó
  - Soporta contexto adicional para debugging
  - Hereda de `HTTPException` de FastAPI

- `HandlerExceptions`:
  - `app_exception_handler`: Maneja `AppHttpException`
  - `generic_exception_handler`: Maneja excepciones no controladas
  - Comportamiento diferente en desarrollo vs producción
  - Logging opcional de errores

#### `/app/middleware` - Middlewares

**Propósito**: Interceptan requests/responses para agregar funcionalidad transversal.

```
app/middleware/
├── ContextMiddleware.py     # Gestión de contexto (Request ID, ContextVars)
└── LoggerMiddleware.py      # Logging de requests/responses
```

**Orden de ejecución** (importante):
1. `ContextMiddleware` - Se ejecuta primero, genera Request ID
2. `LoggerMiddleware` - Se ejecuta segundo, usa Request ID para logs

**Configuración en `main.py`:**
```python
if LOGGER_MIDDLEWARE_ENABLED:
    app.add_middleware(LoggerMiddleware)
app.add_middleware(ContextMiddleware)  # Último agregado = primero ejecutado
```

#### `/app/models` - Modelos

**Propósito**: Interacción con la base de datos. Incluye dos tipos de modelos:

```
app/models/
├── __init__.py           # CRÍTICO: Exporta modelos ORM para Alembic
├── base.py               # DeclarativeBase y mixins (para ORM)
├── user.py               # Modelo ORM (para migraciones con Alembic)
├── user_model.py         # Modelo de datos (SQL directo) - MVC
└── *_model.py            # Otros modelos de datos
```

**Dos tipos de modelos:**

1. **Modelos ORM** (`user.py`, `post.py`, etc.):
   - Solo para **migraciones con Alembic**
   - Usan SQLAlchemy 2.0 (`Mapped[]`, `mapped_column()`)
   - Heredan de `Base` y `TimestampMixin`
   - **Deben importarse en `__init__.py`**

2. **Modelos de datos** (`*_model.py`):
   - Para **interacción con BD en el patrón MVC**
   - Usan SQL directo con `Database.execute_query()`
   - Llamados desde Controllers

**Ejemplo de Modelo de Datos (MVC):**

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
        """Crear nuevo usuario - retorna ID"""
        return self.db.execute_query(
            "INSERT INTO users (username, email, hashed_password) "
            "VALUES (:username, :email, :password)",
            user_data
        )

    def update(self, user_id: int, user_data: dict):
        """Actualizar usuario - retorna rows affected"""
        return self.db.execute_query(
            "UPDATE users SET email = :email WHERE id = :id",
            {"id": user_id, **user_data}
        )

    def delete(self, user_id: int):
        """Eliminar usuario - retorna rows deleted"""
        return self.db.execute_query(
            "DELETE FROM users WHERE id = :id",
            {"id": user_id}
        )
```

**Ejemplo de Modelo ORM (solo para migraciones):**

```python
# app/models/user.py (para Alembic)
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
```

**`__init__.py`** - **CRÍTICO para Alembic:**
```python
# Solo importar modelos ORM (no *_model.py)
from app.models.base import Base, TimestampMixin
from app.models.user import User

__all__ = ["Base", "TimestampMixin", "User"]
```

#### `/app/routes` - Endpoints (Routes en MVC)

**Propósito**: Definición de rutas y endpoints de la API. Delegan a controllers.

```
app/routes/
├── routes.py         # Router principal o combinador
├── users.py          # Endpoints de usuarios
├── posts.py          # Endpoints de posts
└── test.py           # Endpoints de ejemplo/testing
```

**Responsabilidades:**
- Definir rutas HTTP (`GET`, `POST`, `PUT`, `DELETE`)
- Validar entrada con Pydantic schemas
- Delegar lógica a Controllers
- Retornar respuestas

**Ejemplo (Patrón MVC):**

```python
# app/routes/users.py
from fastapi import APIRouter
from app.controllers.user_controller import UserController
from app.schemas.user import UserCreate, UserResponse  # Pydantic schemas

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    """Obtener usuario por ID"""
    controller = UserController()
    return controller.get_user(user_id)

@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    """Crear nuevo usuario"""
    controller = UserController()
    return controller.create_user(user.dict())

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate):
    """Actualizar usuario"""
    controller = UserController()
    return controller.update_user(user_id, user.dict(exclude_unset=True))

@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int):
    """Eliminar usuario"""
    controller = UserController()
    controller.delete_user(user_id)
```

**Combinar routers en `routes.py`:**
```python
from fastapi import APIRouter
from app.routes import users, posts, auth

router = APIRouter()
router.include_router(users.router)
router.include_router(posts.router)
router.include_router(auth.router)
```

#### `/app/schemas` - Schemas Pydantic (Opcional)

**Propósito**: Definir schemas de validación de entrada/salida separados de modelos.

```
app/schemas/
├── __init__.py
├── user.py           # Schemas de usuario
└── post.py           # Schemas de post
```

**Ejemplo:**

```python
# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    """Schema para crear usuario"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None

class UserUpdate(BaseModel):
    """Schema para actualizar usuario"""
    email: EmailStr | None = None
    full_name: str | None = None

class UserResponse(BaseModel):
    """Schema de respuesta (sin password)"""
    id: int
    username: str
    email: str
    is_active: bool

    class Config:
        from_attributes = True  # Para convertir desde dict/ORM
```

**Nota:** Los schemas son opcionales. Puedes usar dicts directamente si prefieres.

#### `/app/utils` - Utilidades

**Propósito**: Funciones reutilizables que no encajan en otras categorías.

```
app/utils/
├── __init__.py
└── dict_utils.py     # Utilidades para diccionarios
```

**Uso típico:**
- Helpers de formateo
- Validadores
- Conversores de datos
- Funciones auxiliares

### `/alembic` - Sistema de Migraciones

**Propósito**: Control de versiones del esquema de base de datos.

```
alembic/
├── versions/                    # Archivos de migración generados
│   ├── .gitkeep
│   └── YYYYMMDD_HHMM_<rev>_<slug>.py
├── env.py                       # Configuración de Alembic
└── script.py.mako               # Template para nuevas migraciones
```

**Archivos clave:**

- **`env.py`**: Conecta Alembic con el proyecto
  - Importa variables de entorno desde `app.core.environments`
  - Importa modelos desde `app.models`
  - Configuración MySQL específica

- **`versions/`**: Migraciones versionadas
  - Cada archivo tiene `revision`, `down_revision`, `upgrade()`, `downgrade()`
  - Nombres con timestamp: `20260211_1430_a1b2c3d4_create_users.py`

**Ver más**: [README_MIGRATIONS.md](../README_MIGRATIONS.md)

### `/docs` - Documentación

**Propósito**: Documentación completa del proyecto.

```
docs/
├── getting-started.md           # Guía de instalación
├── project-structure.md         # Este archivo
├── deployment.md                # Guía de despliegue
├── features/
│   ├── logging.md               # Sistema de logging
│   ├── context.md               # Context management
│   ├── database.md              # Base de datos
│   ├── exceptions.md            # Manejo de errores
│   └── middlewares.md           # Middlewares
└── development/
    ├── pre-commit.md            # Pre-commit hooks
    └── best-practices.md        # Mejores prácticas
```

## Archivos de Configuración

### `main.py` - Punto de Entrada

**Propósito**: Inicializa y configura la aplicación FastAPI.

**Contenido típico:**
```python
from fastapi import FastAPI
from app.middleware.ContextMiddleware import ContextMiddleware
from app.middleware.LoggerMiddleware import LoggerMiddleware
from app.exceptions import AppHttpException, app_exception_handler, generic_exception_handler
from app.routes.routes import router

app = FastAPI()

# Middlewares (orden importa)
app.add_middleware(LoggerMiddleware)
app.add_middleware(ContextMiddleware)

# Exception handlers
app.add_exception_handler(AppHttpException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Routers
app.include_router(router)
```

### `pyproject.toml` - Configuración del Proyecto

**Propósito**: Define dependencias, metadatos y configuración de herramientas.

**Secciones principales:**

```toml
[project]
name = "fastapi-template"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "alembic>=1.14.0",
    "detect-secrets>=1.5.0",
    "dotenv>=0.9.9",
    "fastapi[standard]>=0.123.4",
    "itsdangerous>=2.2.0",
    "pymysql>=1.1.2",
    "sqlalchemy>=2.0.46",
]

[dependency-groups]
dev = [
    "pre-commit>=4.5.1",
]
```

**Agregar dependencias:**
```bash
# Producción
uv add <paquete>

# Desarrollo
uv add --group dev <paquete>
```

### `.pre-commit-config.yaml` - Pre-commit Hooks

**Propósito**: Configuración de hooks que se ejecutan antes de cada commit.

**Hooks configurados:**
- **Ruff**: Linter y formateador
- **Bandit**: Análisis de seguridad
- **detect-secrets**: Prevención de commits de credenciales
- **Checks estándar**: YAML, TOML, JSON, trailing whitespace, etc.

**Ver más**: [docs/development/pre-commit.md](development/pre-commit.md)

### `.env.example` - Template de Variables

**Propósito**: Documenta todas las variables de entorno necesarias.

**Nunca contiene valores reales**, solo ejemplos.

**Usuario debe:**
1. Copiar a `.env`: `cp .env.example .env`
2. Editar `.env` con valores reales
3. `.env` está en `.gitignore` (no se versiona)

### `.gitignore` - Archivos Ignorados

**Propósito**: Define qué archivos Git debe ignorar.

**Incluye:**
- `__pycache__/`, `*.pyc` - Bytecode de Python
- `.venv/`, `venv/` - Entornos virtuales
- `.env`, `.env.*` - Variables de entorno (excepto `.env.example`)
- `.ruff_cache/` - Cache de Ruff
- `.mypy_cache/` - Cache de mypy
- `*.log` - Archivos de log
- `.idea/`, `.vscode/` - Configuración de IDEs

### `README.md` - Documentación Principal

**Propósito**: Primera referencia del proyecto.

**Contiene:**
- Descripción general
- Características principales
- Inicio rápido
- Enlaces a documentación detallada

### `README_MIGRATIONS.md` - Guía de Migraciones

**Propósito**: Documentación completa de Alembic.

**Contiene:**
- Comandos principales
- Workflow típico
- Mejores prácticas
- Troubleshooting
- Integración con el proyecto

### `CLAUDE.md` - Guía para Agentes IA

**Propósito**: Contexto para agentes de IA (Claude, GPT, etc.).

**Contiene:**
- Arquitectura del proyecto
- Patrones y convenciones
- Flujos de trabajo recomendados
- Consideraciones importantes

## Flujo de Datos

### Request → Response

```
1. Cliente envía request
   ↓
2. ContextMiddleware
   - Genera Request ID
   - Establece ContextVars (IP, método, ruta, etc.)
   - Inyecta Request ID en request.state
   ↓
3. LoggerMiddleware
   - Obtiene Request ID de ContextVars
   - Registra request (método, path, body, query)
   ↓
4. Router
   - Encuentra endpoint correspondiente
   ↓
5. Endpoint
   - Ejecuta lógica de negocio
   - Puede usar ContextVars (current_http_identifier, etc.)
   - Puede lanzar AppHttpException
   ↓
6. Exception Handler (si hay error)
   - app_exception_handler o generic_exception_handler
   - Registra error (si LOGGER_EXCEPTIONS_ENABLED=True)
   - Retorna JSON con error
   ↓
7. LoggerMiddleware (respuesta)
   - Registra respuesta (status, duración)
   ↓
8. ContextMiddleware (respuesta)
   - Inyecta header X-Request-ID en respuesta
   - Limpia ContextVars
   ↓
9. Cliente recibe response
```

### Database Query Flow

#### SQL Directo

```
Endpoint
  ↓
Database.execute_query()
  ↓
SQLAlchemy Engine
  ↓
MySQL/MariaDB
  ↓
Resultado (dict o list[dict])
  ↓
Endpoint
```

#### ORM

```
Endpoint
  ↓
Database.get_declarative_base_session()
  ↓
Session.query(Model).filter(...).first()
  ↓
SQLAlchemy Core → SQL
  ↓
MySQL/MariaDB
  ↓
Modelo (objeto Python)
  ↓
Endpoint
```

## Convenciones de Nombres

### Archivos y Carpetas

- **Archivos Python**: `snake_case.py`
  - `user.py`, `blog_post.py`, `auth_helpers.py`
- **Carpetas**: `snake_case/`
  - `app/`, `core/`, `user_management/`
- **Clases**: `PascalCase`
  - `User`, `BlogPost`, `ContextMiddleware`
- **Funciones/Variables**: `snake_case`
  - `get_user()`, `user_id`, `is_active`
- **Constantes**: `UPPER_SNAKE_CASE`
  - `DB_HOST`, `LOGGER_LEVEL`, `MAX_CONNECTIONS`

### Modelos SQLAlchemy

- **Clase**: Singular, `PascalCase`
  - `User`, `Post`, `Comment`
- **Tabla**: Plural, `snake_case`
  - `users`, `posts`, `comments`
- **Columnas**: `snake_case`
  - `id`, `username`, `created_at`, `is_active`

### Rutas API

- **Recursos**: Plural, `kebab-case` (o sin guiones)
  - `/users`, `/blog-posts`, `/comments`
- **Acciones**: Verbos HTTP
  - `GET /users` - Listar usuarios
  - `POST /users` - Crear usuario
  - `GET /users/{id}` - Obtener usuario
  - `PUT /users/{id}` - Actualizar usuario
  - `DELETE /users/{id}` - Eliminar usuario

## Patrones de Desarrollo

### Crear Nuevo Modelo

1. Crear `app/models/post.py`
2. Definir clase heredando `Base` y `TimestampMixin`
3. **Importar en `app/models/__init__.py`** (CRÍTICO)
4. Generar migración: `uv run alembic revision --autogenerate -m "add posts"`
5. Revisar migración generada
6. Aplicar: `uv run alembic upgrade head`

### Crear Nuevo Endpoint

1. Crear `app/routes/posts.py`
2. Definir `router = APIRouter(prefix="/posts", tags=["Posts"])`
3. Crear endpoints con decoradores `@router.get()`, `@router.post()`, etc.
4. Registrar router en `app/routes/routes.py` o `main.py`

### Agregar Variable de Entorno

1. Agregar en `.env.example` con valor de ejemplo
2. Agregar en `app/core/environments.py`:
   ```python
   NEW_VAR = os.getenv("NEW_VAR", "default_value")
   ```
3. Documentar en `docs/` si es necesario

## Dependencias Entre Componentes

```
main.py
 ├── app.middleware.ContextMiddleware (depende de app.core.context)
 ├── app.middleware.LoggerMiddleware (depende de app.core.logger, app.core.context)
 ├── app.exceptions.HandlerExceptions (depende de app.core.logger, app.core.context)
 └── app.routes.* (pueden depender de todo lo demás)

app.core.database
 └── app.core.environments

app.core.logger
 └── app.core.environments

app.models.*
 └── app.models.base

alembic/env.py
 ├── app.core.environments
 └── app.models (todos)
```

## Buenas Prácticas

1. **Nunca importar de `main.py`** en módulos de `app/`
2. **Siempre importar modelos en `app/models/__init__.py`**
3. **Usar `get_logger(__name__)`** en cada módulo para logging
4. **Acceder variables de entorno solo desde `app.core.environments`**
5. **Mantener middlewares en orden correcto** (Context → Logger)
6. **Documentar nuevas features** en `docs/`
7. **Ejecutar pre-commit** antes de cada commit

## Recursos

- [Guía de Inicio Rápido](getting-started.md)
- [Mejores Prácticas de Desarrollo](development/best-practices.md)
- [Sistema de Logging](features/logging.md)
- [Context Management](features/context.md)
- [Base de Datos](features/database.md)

---

**Siguiente**: [Mejores Prácticas de Desarrollo](development/best-practices.md)
