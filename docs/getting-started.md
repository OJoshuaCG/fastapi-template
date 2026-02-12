# Guía de Inicio Rápido

Esta guía te llevará paso a paso desde la instalación hasta tener tu aplicación FastAPI corriendo.

## Requisitos Previos

Antes de comenzar, asegúrate de tener instalado:

- **Python 3.13+**: Verifica con `python --version` o `python3 --version`
- **Git**: Para clonar el repositorio
- **MySQL/MariaDB 5.7+**: Base de datos (opcional, puedes usar PostgreSQL o SQLite)
- **uv**: Gestor de paquetes Python (se instalará en el siguiente paso)

## Paso 1: Instalar uv

uv es un gestor de paquetes ultrarrápido para Python que reemplaza a pip y virtualenv.

### Linux / macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows (PowerShell)

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Verificar instalación

```bash
uv --version
```

## Paso 2: Clonar el Proyecto

```bash
git clone <url-de-tu-repositorio>
cd fastapi-template
```

Si estás comenzando un nuevo proyecto desde esta plantilla:

```bash
# Eliminar historial de git de la plantilla
rm -rf .git

# Inicializar nuevo repositorio
git init
git add .
git commit -m "Initial commit from fastapi-template"
```

## Paso 3: Configurar Variables de Entorno

### Crear archivo .env

```bash
cp .env.example .env
```

### Editar .env

Abre `.env` y configura tus valores:

```env
# ======= Application variables ======= #
APP_ENV=development
APP_NAME="Mi Proyecto FastAPI"
SECRET_KEY=genera_una_clave_secreta_aqui  # Ver sección de generar SECRET_KEY

# ======= Logger variables ======= #
LOGGER_LEVEL=INFO
LOGGER_MIDDLEWARE_ENABLED=True
LOGGER_MIDDLEWARE_SHOW_HEADERS=False
LOGGER_EXCEPTIONS_ENABLED=True

# ======= Database variables ======= #
DB_HOST=localhost
DB_USER=tu_usuario
DB_PASS=tu_contraseña
DB_NAME=nombre_de_tu_bd
DB_PORT=3306
```

### Generar SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copia el resultado y pégalo en `SECRET_KEY` de tu `.env`.

## Paso 4: Instalar Dependencias

```bash
# Instalar todas las dependencias del proyecto
uv sync

```

**Nota**: `uv sync` crea automáticamente un entorno virtual en `.venv/` e instala todas las dependencias de `pyproject.toml`.

## Paso 5: Configurar Base de Datos

### Opción A: MySQL/MariaDB (Recomendado)

#### Crear base de datos

```bash
mysql -u root -p
```

En el shell de MySQL:

```sql
CREATE DATABASE nombre_de_tu_bd CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- Crear usuario (opcional)
CREATE USER 'tu_usuario'@'localhost' IDENTIFIED BY 'tu_contraseña';
GRANT ALL PRIVILEGES ON nombre_de_tu_bd.* TO 'tu_usuario'@'localhost';
FLUSH PRIVILEGES;

EXIT;
```

#### Aplicar migraciones

```bash
# Ver estado actual
uv run alembic current

# Aplicar todas las migraciones
uv run alembic upgrade head

# Verificar
uv run alembic current
```

### Opción B: SQLite (Desarrollo rápido)

Si prefieres SQLite para desarrollo rápido, modifica `app/core/database.py`:

```python
# Cambiar la línea DB_URL a:
DB_URL = f"sqlite:///./{db_name}.db"
```

Y en `.env`:

```env
DB_NAME=development
DB_USER=
DB_PASS=
DB_HOST=
DB_PORT=
```

Luego aplica migraciones:

```bash
uv run alembic upgrade head
```

## Paso 6: Ejecutar la Aplicación

### Modo Desarrollo (con hot-reload)

```bash
uv run uvicorn main:app --reload
```

### Especificar puerto y host

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### Modo Producción

```bash
# Establecer APP_ENV=production en .env primero
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Paso 7: Verificar Instalación

### Acceder a la documentación interactiva

Abre tu navegador y ve a:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Probar endpoint de ejemplo

Si existe un endpoint de prueba, puedes probarlo desde Swagger o con curl:

```bash
curl http://localhost:8000/
```

### Verificar logs

Si `LOGGER_MIDDLEWARE_ENABLED=True`, verás logs en la consola:

```
2026-02-11 10:30:15 [INFO] a1b2c3d4e5f6g7h8 | Host: 127.0.0.1 | Request: GET / | Body: <no body> | Query: <no parameters>
2026-02-11 10:30:15 [INFO] a1b2c3d4e5f6g7h8 | Host: 127.0.0.1 | Response: GET / | Status: 200 | Duration: 0.023s
```

## Estructura del Proyecto Creado

```
fastapi-template/
├── .venv/                 # ✓ Entorno virtual (creado por uv sync)
├── .git/                  # ✓ Repositorio git
├── .env                   # ✓ Variables de entorno (TU CONFIGURACIÓN)
├── app/
├── alembic/
│   └── versions/          # ✓ Migraciones aplicadas
├── main.py
└── ...
```

## Comandos Útiles

### uv (Gestión de Dependencias)

```bash
# Agregar dependencia
uv add <paquete>

# Agregar dependencia de desarrollo
uv add --group dev <paquete>

# Eliminar dependencia
uv remove <paquete>

# Sincronizar dependencias
uv sync

# Actualizar dependencias
uv lock --upgrade
```

### Alembic (Migraciones)

```bash
# Crear migración automática
uv run alembic revision --autogenerate -m "descripción"

# Aplicar migraciones
uv run alembic upgrade head

# Revertir última migración
uv run alembic downgrade -1

# Ver estado
uv run alembic current

# Ver historial
uv run alembic history
```

Ver guía completa en [README_MIGRATIONS.md](../README_MIGRATIONS.md).

### Uvicorn

```bash
# Desarrollo
uv run uvicorn main:app --reload

# Producción (4 workers)
uv run uvicorn main:app --workers 4

# Especificar host y puerto
uv run uvicorn main:app --host 0.0.0.0 --port 8080

# Con SSL
uv run uvicorn main:app --ssl-keyfile=./key.pem --ssl-certfile=./cert.pem
```

## Solución de Problemas

### Error: "ModuleNotFoundError: No module named 'app'"

**Solución**: Asegúrate de ejecutar comandos con `uv run`:

```bash
# ❌ Incorrecto
python main.py

# ✓ Correcto
uv run uvicorn main:app --reload
```

### Error: "Access denied for user 'username'@'localhost'"

**Problema**: Variables de entorno incorrectas o base de datos no configurada.

**Solución**:
1. Verifica que `.env` tenga valores correctos
2. Verifica que la base de datos y usuario existan en MySQL
3. Prueba conexión manualmente: `mysql -u tu_usuario -p`

### Error: "Can't locate revision identified by '...'"

**Problema**: Base de datos y migraciones desincronizadas.

**Solución**:

```bash
# Ver estado actual
uv run alembic current

# Si está vacío, marcar como head
uv run alembic stamp head

# Luego aplicar migraciones
uv run alembic upgrade head
```

### Puerto 8000 en uso

**Solución**: Usa otro puerto:

```bash
uv run uvicorn main:app --reload --port 8080
```

O detén el proceso que usa el puerto 8000:

```bash
# Linux/Mac
lsof -ti:8000 | xargs kill -9

# Windows (PowerShell)
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process
```

## Próximos Pasos

Ahora que tienes el proyecto corriendo, puedes:

1. **Explorar la estructura**: Lee [Estructura del Proyecto](project-structure.md)
2. **Crear modelos**: Sigue la guía de [Base de Datos](features/database.md)
3. **Agregar endpoints**: Ve [Mejores Prácticas](development/best-practices.md)
4. **Configurar logging**: Lee [Sistema de Logging](features/logging.md)
5. **Entender el contexto**: Ve [Context Management](features/context.md)

## Recursos Adicionales

- [Documentación de FastAPI](https://fastapi.tiangolo.com/)
- [Guía de uv](https://github.com/astral-sh/uv)
- [Documentación de SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Documentación de Alembic](https://alembic.sqlalchemy.org/)

---

¿Listo para comenzar a desarrollar? Lee la [Guía de Mejores Prácticas](development/best-practices.md) para escribir código de calidad.
