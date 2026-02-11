# FastAPI Template

> **Plantilla robusta y lista para producción de FastAPI con las mejores prácticas integradas**

Esta plantilla proporciona una base sólida para desarrollar aplicaciones FastAPI con todas las herramientas y configuraciones necesarias para un desarrollo profesional.

## Características Principales

- **Gestor de Paquetes**: [uv](https://github.com/astral-sh/uv) - Gestor de paquetes ultrarrápido para Python
- **Logging Avanzado**: Sistema de logging centralizado con middleware de trazabilidad
- **Context Management**: ContextVars para mantener estado de request (similar a sesiones PHP)
- **Base de Datos**: Soporte para SQL directo y ORM con SQLAlchemy 2.0
- **Migraciones**: Alembic configurado y listo para usar
- **Manejo de Errores**: Sistema robusto de excepciones con tracking automático
- **Pre-commit Hooks**: Ruff, Bandit, detect-secrets y más
- **Trazabilidad**: Request ID único en cada petición para debugging
- **Producción Ready**: Configuración para desarrollo y producción

## Inicio Rápido

### 1. Clonar el Proyecto

```bash
git clone <tu-repositorio>
cd fastapi-template
```

### 2. Configurar Entorno

Copiar y configurar variables de entorno:

```bash
cp .env.example .env
```

Editar `.env` con tus valores:

```env
# Aplicación
APP_ENV=development
APP_NAME="Mi Proyecto FastAPI"
SECRET_KEY=tu_clave_secreta_aqui

# Base de Datos
DB_HOST=localhost
DB_USER=tu_usuario
DB_PASS=tu_contraseña
DB_NAME=nombre_bd
DB_PORT=3306
DB_ENGINE=sqlite

# Logging
LOGGER_LEVEL=INFO
LOGGER_MIDDLEWARE_ENABLED=True
LOGGER_MIDDLEWARE_SHOW_HEADERS=False
LOGGER_EXCEPTIONS_ENABLED=True
```

### 3. Instalar Dependencias

```bash
# Instalar uv si no lo tienes
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar dependencias del proyecto
uv sync

# Instalar pre-commit hooks
uv run pre-commit install
```

### 4. Configurar Base de Datos

```bash
# Crear base de datos en MySQL/MariaDB
mysql -u root -p -e "CREATE DATABASE nombre_bd CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"

# Aplicar migraciones
uv run alembic upgrade head
```

### 5. Ejecutar Aplicación

```bash
# Desarrollo con hot-reload
uv run uvicorn main:app --reload

# Especificar puerto y host
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

La aplicación estará disponible en:
- **API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Docs (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Estructura del Proyecto

```
fastapi-template/
├── app/
│   ├── core/              # Configuración central
│   │   ├── context.py     # ContextVars para request state
│   │   ├── database.py    # Gestión de base de datos
│   │   ├── environments.py # Variables de entorno
│   │   └── logger.py      # Sistema de logging
│   ├── exceptions/        # Excepciones personalizadas
│   │   ├── AppHttpException.py
│   │   └── HandlerExceptions.py
│   ├── middleware/        # Middlewares de aplicación
│   │   ├── ContextMiddleware.py  # Gestión de contexto
│   │   └── LoggerMiddleware.py   # Logging de requests
│   ├── models/            # Modelos SQLAlchemy
│   │   ├── base.py        # Base y mixins
│   │   └── user.py        # Modelo de ejemplo
│   ├── routes/            # Endpoints de la API
│   └── utils/             # Utilidades
├── alembic/               # Migraciones de base de datos
│   ├── versions/          # Archivos de migración
│   └── env.py             # Configuración de Alembic
├── docs/                  # Documentación del proyecto
├── main.py                # Punto de entrada de la aplicación
├── pyproject.toml         # Configuración de dependencias
├── .pre-commit-config.yaml # Configuración de pre-commit
└── .env.example           # Ejemplo de variables de entorno
```

Ver más detalles en [Estructura del Proyecto](docs/project-structure.md).

## Documentación

### Guías de Usuario

- [Inicio Rápido](docs/getting-started.md) - Guía completa de instalación y configuración
- [Estructura del Proyecto](docs/project-structure.md) - Organización de archivos y carpetas

### Características

- [Sistema de Logging](docs/features/logging.md) - Configuración y uso del logger
- [Context Management](docs/features/context.md) - Sistema de contexto de requests
- [Base de Datos](docs/features/database.md) - SQL directo y ORM
- [Migraciones](README_MIGRATIONS.md) - Guía completa de Alembic
- [Manejo de Excepciones](docs/features/exceptions.md) - Errores personalizados
- [Middlewares](docs/features/middlewares.md) - Middlewares disponibles

### Desarrollo

- [Pre-commit Hooks](docs/development/pre-commit.md) - Configuración de calidad de código
- [Mejores Prácticas](docs/development/best-practices.md) - Guía de desarrollo
- [Despliegue](docs/deployment.md) - Guía de producción

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

## Pre-commit Hooks

El proyecto incluye hooks automáticos de pre-commit para mantener calidad de código:

- **Ruff**: Linter y formateador (reemplaza flake8, isort, black)
- **Bandit**: Análisis de seguridad
- **detect-secrets**: Prevención de commits de credenciales
- **Validadores**: YAML, TOML, JSON, trailing whitespace, etc.

```bash
# Instalar hooks (solo una vez)
uv run pre-commit install

# Ejecutar manualmente en todos los archivos
uv run pre-commit run --all-files
```

Ver [Pre-commit Hooks](docs/development/pre-commit.md) para más detalles.

## Ejemplos de Uso

### Logging

```python
from app.core.logger import get_logger

logger = get_logger(__name__)

logger.info("Usuario creado exitosamente")
logger.warning("Intento de acceso no autorizado")
logger.error("Error en conexión a base de datos")
```

### Base de Datos - SQL Directo

```python
from app.core.database import Database
from app.core.environments import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT

db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)

# SELECT
users = db.execute_query("SELECT * FROM users WHERE is_active = :active",
                         {"active": True}, fetchone=False)

# INSERT
user_id = db.execute_query(
    "INSERT INTO users (username, email) VALUES (:username, :email)",
    {"username": "john", "email": "john@example.com"}
)
```

### Base de Datos - ORM

```python
from app.models import User
from app.core.database import Database

db = Database(DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT)
session = db.get_declarative_base_session()

try:
    # Consultar
    user = session.query(User).filter(User.username == "john").first()

    # Crear
    new_user = User(username="jane", email="jane@example.com", hashed_password="...")
    session.add(new_user)
    session.commit()
finally:
    session.close()
```

### Context Management

```python
from app.core.context import current_http_identifier, current_request_ip, current_user_id

# Obtener Request ID único
request_id = current_http_identifier.get()

# Obtener IP del cliente
client_ip = current_request_ip.get()

# Establecer usuario actual (en middleware de auth)
current_user_id.set(user.id)
```

### Excepciones Personalizadas

```python
from app.exceptions import AppHttpException

# Lanzar excepción con contexto
raise AppHttpException(
    message="Usuario no encontrado",
    status_code=404,
    context={"user_id": user_id}
)
```

## Tecnologías

- **[FastAPI](https://fastapi.tiangolo.com/)** - Framework web moderno y rápido
- **[uv](https://github.com/astral-sh/uv)** - Gestor de paquetes Python ultrarrápido
- **[SQLAlchemy 2.0](https://docs.sqlalchemy.org/)** - ORM y SQL toolkit
- **[Alembic](https://alembic.sqlalchemy.org/)** - Migraciones de base de datos
- **[Pydantic](https://docs.pydantic.dev/)** - Validación de datos
- **[Ruff](https://docs.astral.sh/ruff/)** - Linter y formateador extremadamente rápido
- **[Bandit](https://bandit.readthedocs.io/)** - Herramienta de seguridad para Python
- **[Pre-commit](https://pre-commit.com/)** - Framework de git hooks

## Requisitos

- Python 3.13+
- MySQL/MariaDB 5.7+ (opcional, configurable para PostgreSQL o SQLite)
- uv (gestor de paquetes)

## Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Soporte

- **Documentación**: Ver carpeta `docs/`
- **Issues**: Reportar problemas en GitHub Issues
- **Discusiones**: GitHub Discussions

## Licencia

Este proyecto es una plantilla de código abierto. Úsala libremente para tus proyectos.

---

**Desarrollado con FastAPI + uv** | [Documentación Completa](docs/getting-started.md)
