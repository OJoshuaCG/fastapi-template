# FastAPI Template - Guía para Agentes de IA

Este documento proporciona contexto y guías para agentes de IA que trabajen en este proyecto.

## Descripción del Proyecto

Este es un **template de FastAPI** diseñado para ser la base de nuevos proyectos. Incluye configuración robusta, mejores prácticas y herramientas esenciales para desarrollo profesional.

### Propósito

- Servir como punto de partida para proyectos FastAPI
- Proporcionar estructura y patrones consistentes
- Incluir herramientas de calidad de código desde el inicio
- Facilitar el desarrollo rápido sin sacrificar calidad

### Arquitectura: Pseudo-MVC (Sin Vista)

El proyecto sigue un patrón **MVC sin Vista** ya que es puro backend:

**Routes → Controllers → Models → Database**

- **Routes** (`app/routes/`): Definen endpoints y validan entrada (Pydantic schemas)
- **Controllers** (`app/controllers/`): Lógica de negocio y orquestación
- **Models** (`app/models/`): Interacción con base de datos (SQL directo o ORM)

## Arquitectura del Proyecto

### Estructura de Carpetas

```
fastapi-template/
├── app/                    # Código principal de la aplicación
│   ├── core/               # Módulos centrales (database, logger, context, environments)
│   ├── controllers/        # Controladores con lógica de negocio (MVC)
│   ├── exceptions/         # Excepciones personalizadas y handlers
│   ├── middleware/         # Middlewares (Context, Logger)
│   ├── models/             # Modelos para interacción con BD
│   │   ├── *.py            # Modelos ORM (SQLAlchemy) - para migraciones
│   │   └── *_model.py      # Modelos de datos (SQL directo) - opcional
│   ├── routes/             # Endpoints de la API (Routes en MVC)
│   ├── schemas/            # Schemas Pydantic para validación (opcional)
│   └── utils/              # Funciones utilitarias
├── alembic/                # Sistema de migraciones de base de datos
│   ├── versions/           # Archivos de migración generados
│   └── env.py              # Configuración de Alembic
├── docs/                   # Documentación del proyecto
│   ├── features/           # Documentación de características
│   └── development/        # Guías de desarrollo
├── main.py                 # Punto de entrada de FastAPI
├── pyproject.toml          # Dependencias y configuración del proyecto
├── .pre-commit-config.yaml # Configuración de hooks de pre-commit
├── .env.example            # Template de variables de entorno
└── .gitignore              # Archivos ignorados por git
```

### Componentes Clave

#### 1. Core (`app/core/`)

- **`environments.py`**: Centraliza todas las variables de entorno. Usa `python-dotenv` para cargar desde `.env`.
  - Variables de aplicación: `APP_ENV`, `APP_NAME`, `SECRET_KEY`
  - Variables de logging: `LOGGER_LEVEL`, `LOGGER_MIDDLEWARE_ENABLED`, etc.
  - Variables de base de datos: `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_PORT`

- **`logger.py`**: Sistema de logging centralizado
  - Función `get_logger(name, level)` que retorna un logger configurado
  - Evita duplicación de handlers
  - Formato consistente: `%(asctime)s [%(levelname)s] %(message)s`

- **`context.py`**: ContextVars para mantener estado de request
  - Similar a sesiones en PHP, pero basado en contexto asíncrono
  - Variables disponibles: `current_http_identifier`, `current_request_ip`, `current_request_method`, `current_request_route`, `current_user_id`, etc.
  - Establecidas automáticamente por `ContextMiddleware`

- **`database.py`**: Gestión de conexiones a base de datos
  - Clase `Database` con soporte para SQL directo y ORM
  - Métodos principales:
    - `execute_query()`: Ejecuta SQL directo con parámetros
    - `call_procedure()`: Llama stored procedures de MySQL
    - `get_declarative_base_session()`: Retorna sesión para ORM SQLAlchemy
  - Configuración: MySQL con `utf8mb4` charset y `utf8mb4_general_ci` collation
  - Pool de conexiones configurado (size=10, max_overflow=20, recycle=180s)

#### 2. Exceptions (`app/exceptions/`)

- **`AppHttpException.py`**: Excepción personalizada que hereda de `HTTPException`
  - Captura automáticamente ubicación del error (archivo, función, línea, código)
  - Soporta contexto adicional para debugging
  - Ejemplo:
    ```python
    raise AppHttpException(
        message="Usuario no encontrado",
        status_code=404,
        context={"user_id": user_id}
    )
    ```

- **`HandlerExceptions.py`**: Manejadores globales de excepciones
  - `app_exception_handler`: Maneja `AppHttpException`
  - `generic_exception_handler`: Maneja excepciones no controladas
  - En desarrollo (`APP_ENV=development`): Retorna detalles completos del error
  - En producción: Oculta detalles técnicos por seguridad
  - Logging opcional controlado por `LOGGER_EXCEPTIONS_ENABLED`

#### 3. Middleware (`app/middleware/`)

- **`ContextMiddleware.py`**: **DEBE ejecutarse primero**
  - Genera Request ID único (`secrets.token_hex(8)`)
  - Establece ContextVars con información de la request
  - Inyecta header `X-Request-ID` en respuestas
  - Limpia ContextVars al finalizar (previene memory leaks)

- **`LoggerMiddleware.py`**: Logging de requests/responses
  - Depende de `ContextMiddleware` para obtener Request ID
  - Registra método, path, query params, body, headers (opcional)
  - Calcula tiempo de procesamiento
  - Oculta información sensible en rutas específicas (ej: `/user/login`)
  - Controlado por `LOGGER_MIDDLEWARE_ENABLED`

**Orden de middlewares en `main.py`:**
```python
if LOGGER_MIDDLEWARE_ENABLED:
    app.add_middleware(LoggerMiddleware)  # Se ejecuta segundo
app.add_middleware(ContextMiddleware)     # Se ejecuta primero
```

#### 4. Models (`app/models/`)

- **`base.py`**: Configuración base de SQLAlchemy 2.0
  - `NAMING_CONVENTION`: Convenciones para nombres de constraints
  - `Base`: DeclarativeBase con metadata configurada
  - `TimestampMixin`: Mixin reutilizable para campos `created_at` y `updated_at`

- **`user.py`**: Modelo de ejemplo
  - Usa sintaxis moderna de SQLAlchemy 2.0: `Mapped[]`, `mapped_column()`
  - Hereda `TimestampMixin` para timestamps automáticos
  - Campos: id, username, email, hashed_password, full_name, notes, is_active, is_superuser

- **`__init__.py`**: **CRÍTICO** - Todos los modelos deben importarse aquí
  - Alembic detecta modelos solo si están en `__all__`
  - Ejemplo: `from app.models.user import User` + `__all__ = ["Base", "TimestampMixin", "User"]`

#### 5. Alembic (Migraciones)

- Configuración en `alembic/env.py` integrada con el proyecto
- Importa variables de entorno desde `app.core.environments`
- Importa modelos desde `app.models` (usa `Base.metadata`)
- Configuración MySQL específica (charset, timezone UTC)
- Ver `README_MIGRATIONS.md` para guía completa

## Flujo de Trabajo Recomendado

### Creación de Nuevas Features

1. **Crear modelo** (si necesita BD):
   ```python
   # app/models/post.py
   from app.models.base import Base, TimestampMixin
   class Post(Base, TimestampMixin):
       __tablename__ = "posts"
       # ... definir campos
   ```

2. **Importar modelo** en `app/models/__init__.py`:
   ```python
   from app.models.post import Post
   __all__ = [..., "Post"]
   ```

3. **Generar migración**:
   ```bash
   uv run alembic revision --autogenerate -m "add posts table"
   ```

4. **Revisar migración** en `alembic/versions/` antes de aplicar

5. **Aplicar migración**:
   ```bash
   uv run alembic upgrade head
   ```

6. **Crear modelo** en `app/models/` (si necesita BD):
   ```python
   # app/models/post_model.py
   from app.core.database import Database
   from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT

   class PostModel:
       def __init__(self):
           self.db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)

       def find_by_id(self, post_id: int):
           return self.db.execute_query(
               "SELECT * FROM posts WHERE id = :id",
               {"id": post_id},
               fetchone=True
           )

       def create(self, post_data: dict):
           return self.db.execute_query(
               "INSERT INTO posts (...) VALUES (...)",
               post_data
           )
   ```

7. **Crear controlador** en `app/controllers/`:
   ```python
   # app/controllers/post_controller.py
   from app.models.post_model import PostModel
   from app.exceptions import AppHttpException

   class PostController:
       def __init__(self):
           self.post_model = PostModel()

       def get_post(self, post_id: int):
           post = self.post_model.find_by_id(post_id)
           if not post:
               raise AppHttpException("Post no encontrado", 404)
           return post

       def create_post(self, post_data: dict):
           # Lógica de negocio aquí
           post_id = self.post_model.create(post_data)
           return self.post_model.find_by_id(post_id)
   ```

8. **Crear rutas** en `app/routes/`:
   ```python
   # app/routes/posts.py
   from fastapi import APIRouter
   from app.controllers.post_controller import PostController

   router = APIRouter(prefix="/posts", tags=["Posts"])

   @router.get("/{post_id}")
   async def get_post(post_id: int):
       controller = PostController()
       return controller.get_post(post_id)
   ```

9. **Registrar router** en `main.py`:
   ```python
   from app.routes.posts import router as posts_router
   app.include_router(posts_router)
   ```

### Desarrollo de Endpoints (Patrón MVC)

**Flujo recomendado: Routes → Controllers → Models**

1. **Usar logger** para debugging:
   ```python
   from app.core.logger import get_logger
   logger = get_logger(__name__)

   @router.get("/")
   async def endpoint():
       logger.info("Processing request")
       # ...
   ```

2. **Acceder a contexto**:
   ```python
   from app.core.context import current_http_identifier, current_request_ip

   request_id = current_http_identifier.get()
   client_ip = current_request_ip.get()
   ```

3. **Usar excepciones personalizadas**:
   ```python
   from app.exceptions import AppHttpException

   if not user:
       raise AppHttpException(
           message="Usuario no encontrado",
           status_code=404,
           context={"username": username}
       )
   ```

4. **Modelo (interacción con BD - SQL directo)**:
   ```python
   # app/models/user_model.py
   from app.core.database import Database
   from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT

   class UserModel:
       def __init__(self):
           self.db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)

       def find_by_id(self, user_id: int):
           return self.db.execute_query(
               "SELECT * FROM users WHERE id = :id",
               {"id": user_id},
               fetchone=True
           )

       def create(self, user_data: dict):
           return self.db.execute_query(
               "INSERT INTO users (...) VALUES (...)",
               user_data
           )
   ```

5. **Controlador (lógica de negocio)**:
   ```python
   # app/controllers/user_controller.py
   from app.models.user_model import UserModel
   from app.exceptions import AppHttpException

   class UserController:
       def __init__(self):
           self.user_model = UserModel()

       def get_user(self, user_id: int):
           user = self.user_model.find_by_id(user_id)
           if not user:
               raise AppHttpException("Usuario no encontrado", 404)
           return user
   ```

6. **Ruta (endpoint)**:
   ```python
   # app/routes/users.py
   from app.controllers.user_controller import UserController

   @router.get("/{user_id}")
   async def get_user(user_id: int):
       controller = UserController()
       return controller.get_user(user_id)
   ```

## Patrones y Convenciones

### Nombres de Archivos

- **Modelos**: `snake_case.py` (ej: `user.py`, `blog_post.py`)
- **Rutas**: `snake_case.py` (ej: `users.py`, `posts.py`)
- **Clases**: `PascalCase` (ej: `User`, `BlogPost`, `ContextMiddleware`)
- **Funciones/variables**: `snake_case` (ej: `get_user`, `user_id`)

### Imports

**Orden de imports** (siguiendo PEP 8):
1. Bibliotecas estándar de Python
2. Bibliotecas de terceros
3. Módulos del proyecto

**Ejemplo:**
```python
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models import User
```

### Logging

- **INFO**: Operaciones normales exitosas
- **WARNING**: Situaciones inusuales pero manejables
- **ERROR**: Errores que impiden completar una operación
- **DEBUG**: Información detallada para debugging (solo desarrollo)

**Contexto en logs:**
```python
logger.info(f"{request_id} | Usuario {user_id} creado exitosamente")
```

### Excepciones

- **Usar `AppHttpException`** para errores controlados
- **Incluir contexto** relevante para debugging
- **Status codes apropiados**: 400 (Bad Request), 404 (Not Found), 500 (Internal Server Error)

### Variables de Entorno

- **NUNCA** hardcodear valores sensibles
- **SIEMPRE** usar `app.core.environments`
- **Documentar** nuevas variables en `.env.example`

## Pre-commit Hooks

El proyecto usa pre-commit para mantener calidad de código.

**Hooks configurados:**
- **Ruff**: Linter + formateador (reemplaza flake8, isort, black, pyupgrade)
- **Bandit**: Análisis de seguridad
- **detect-secrets**: Prevención de commits de credenciales
- **Checks estándar**: trailing whitespace, EOF, YAML/TOML/JSON syntax, merge conflicts

**Ejecutar manualmente:**
```bash
uv run pre-commit run --all-files
```

**Si un hook falla:**
1. Revisar los cambios automáticos (Ruff puede auto-fix)
2. Corregir manualmente si es necesario
3. Re-stage y commit

## Tecnologías Clave

- **FastAPI**: Framework web con validación automática y documentación
- **SQLAlchemy 2.0**: ORM con sintaxis moderna (`Mapped[]`, `mapped_column()`)
- **Alembic**: Migraciones de base de datos automáticas
- **uv**: Gestor de paquetes ultrarrápido
- **Ruff**: Linter y formateador extremadamente rápido
- **Python 3.13+**: Usa features modernas de Python

## Consideraciones Importantes

### Seguridad

1. **Variables de entorno**: Nunca commitear `.env`
2. **Secretos**: `detect-secrets` previene commits accidentales
3. **SQL Injection**: Siempre usar parámetros (`:param`) en SQL directo
4. **Bandit**: Analiza código en busca de vulnerabilidades comunes

### Performance

1. **Pool de conexiones**: Database class ya configurado (10 conexiones, overflow 20)
2. **Connection recycling**: 180s para evitar conexiones stale
3. **Pre-ping**: Valida conexiones antes de usar

### Testing

- Carpeta `tests/` no existe aún (puedes crearla)
- Usar `pytest` como framework de testing
- Bandit excluye `tests/` de análisis de seguridad

### Logging en Producción

- Establecer `APP_ENV=production` en `.env`
- Configurar `LOGGER_LEVEL=WARNING` o `ERROR`
- `LOGGER_EXCEPTIONS_ENABLED=True` para tracking de errores
- Considerar servicio externo de logs (Sentry, LogRocket, etc.)

## Comandos Útiles

```bash
# Desarrollo
uv run uvicorn main:app --reload
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Pre-commit
uv run pre-commit install
uv run pre-commit run --all-files

# Migraciones
uv run alembic revision --autogenerate -m "descripción"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic current
uv run alembic history

# Dependencias
uv add <paquete>
uv remove <paquete>
uv sync
```

## Próximos Pasos Comunes

### Autenticación

1. Crear modelo `User` con campos de auth
2. Instalar: `uv add python-jose[cryptography] passlib[bcrypt]`
3. Crear endpoints `/login`, `/register`
4. Middleware de autenticación para proteger rutas
5. Usar `current_user_id.set()` en middleware

### Testing

1. Instalar: `uv add pytest pytest-asyncio httpx --group dev`
2. Crear `tests/conftest.py` con fixtures
3. Crear `tests/test_*.py` para cada módulo
4. Configurar GitHub Actions para CI/CD

### CORS

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Documentación API

- FastAPI genera automáticamente: `/docs` (Swagger), `/redoc` (ReDoc)
- Personalizar en `main.py`:
  ```python
  app = FastAPI(
      title="Mi API",
      description="Descripción",
      version="1.0.0"
  )
  ```

## Recursos

- **Documentación del proyecto**: `docs/`
- **README principal**: `readme.md`
- **Migraciones**: `README_MIGRATIONS.md`
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/en/20/
- **Alembic**: https://alembic.sqlalchemy.org/
- **Ruff**: https://docs.astral.sh/ruff/

---

**Nota para Agentes de IA**: Este proyecto sigue patrones establecidos. Mantén la consistencia con la arquitectura existente al agregar nuevas features. Consulta `docs/` para información detallada de cada componente.
