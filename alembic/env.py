"""
Script de entorno de Alembic.

Integra Alembic con la configuración del proyecto FastAPI:
- Lee variables de entorno desde app.core.environments
- Importa modelos ORM desde app.models
- Configura autogenerate con detección de cambios en tipos y defaults
- Soporte para migraciones online y offline
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Importar configuración del proyecto
from app.core.environments import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER

# Importar Base con todos los modelos registrados
# CRÍTICO: Todos los modelos deben estar importados en app/models/__init__.py
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url() -> str:
    """
    Construye la URL de la base de datos desde variables de entorno.

    Usa las mismas variables que app.core.database.Database para garantizar
    consistencia en la configuración.

    Returns:
        str: URL de conexión MySQL con charset utf8mb4
    """
    return f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detecta cambios en tipos de datos
        compare_server_default=True,  # Detecta cambios en valores default
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Construir configuración con URL dinámica
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={
            "charset": "utf8mb4",
            "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_general_ci",
        },
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detecta cambios en tipos de datos
            compare_server_default=True,  # Detecta cambios en valores default
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
