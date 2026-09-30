# database/

Esquema de la base de datos en SQL plano (MariaDB / MySQL). No se usa ORM ni Alembic:
la app accede con SQL directo y stored procedures (`app/core/database.py`).

```
database/
├── init/          # Tablas y datos base: NNN_descripcion.sql (se aplican en orden)
│   └── 001_users.sql
└── procedures/    # Stored procedures: sp_nombre.sql
    └── sp_user_stats.sql   # ejemplo: DELIMITER, 2 result sets, SIGNAL
```

`alembic.ini` en la raíz se conserva como punto de partida **opcional** para quien quiera
migraciones con Alembic (ver [Alembic (opcional)](#alembic-opcional)). La plantilla no instala
la librería y `.dockerignore` lo excluye de la imagen.

## Cómo se aplican

- **docker-compose / desarrollo**: `docker compose up` crea la base y el usuario (`DB_NAME`, `DB_USER`,
  `DB_PASS`) pero la deja **vacía**. Cada desarrollador aplica `init/*.sql` en orden y luego
  `procedures/*.sql` con su gestor de BD (DBeaver, HeidiSQL, DataGrip...) o con el cliente `mariadb`:

  ```bash
  mariadb -h localhost -u $DB_USER -p $DB_NAME < database/init/001_users.sql
  mariadb -h localhost -u $DB_USER -p $DB_NAME < database/procedures/sp_user_stats.sql
  ```

  Los procedures usan `DELIMITER`: aplicarlos con el cliente `mariadb` o un gestor que lo soporte.
- **Tests**: `tests/conftest.py` borra **todas** las tablas de la BD de test y aplica `database/init/*.sql`
  + `database/procedures/*.sql` al iniciar. `sql_statements()` separa las sentencias respetando `DELIMITER`.
- **Servidores existentes**: los cambios posteriores se entregan como un script nuevo
  (`002_add_posts.sql`, `003_alter_users_add_phone.sql`...) y se aplican a mano o por el DBA:

  ```bash
  mariadb -h <host> -u <user> -p <db> < database/init/002_add_posts.sql
  ```

## Convenciones

- Numerar con 3 dígitos y nunca modificar un script ya aplicado en otro entorno: crear uno nuevo.
- Usar `CREATE TABLE IF NOT EXISTS` y `utf8mb4` / `utf8mb4_unicode_ci` (igual que `DB_COLLATION`).
  La collation de la base y las tablas debe coincidir con `DB_COLLATION` (la de la sesión de la app); si no,
  MariaDB puede fallar con `Illegal mix of collations`. Los compose ya arrancan el servidor con
  `--collation-server=${DB_COLLATION:-utf8mb4_unicode_ci}`; en otro servidor crear la base con
  `CREATE DATABASE <db> CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`.
- Stored procedures en `procedures/`, con `DROP PROCEDURE IF EXISTS` + `CREATE PROCEDURE` y
  `DELIMITER` (ver `sp_user_stats.sql`). En una BD existente:
  `mariadb -h <host> -u <user> -p <db> < database/procedures/sp_nombre.sql`.
- Desde Python: `await db.call_procedure("sp_user_stats", [1])` → `list[list[dict]]` (un elemento por result set).
- Los mensajes de `SIGNAL SQLSTATE '45000'` llegan al cliente como 409: escribirlos para el usuario final.

## Alembic (opcional)

La plantilla **no incluye la librería** `alembic`: sin agregarla, `alembic.ini` no hace nada.
Si un proyecto prefiere migraciones versionadas con Alembic en vez de scripts SQL:

1. Agregar la librería:

   ```bash
   uv add alembic
   ```

2. Generar la carpeta con la plantilla async (respeta el `alembic.ini` existente):

   ```bash
   uv run alembic init -t async alembic
   ```

3. En `alembic/env.py`, conectar con la misma configuración que la app (credenciales escapadas,
   `connect_timeout`) reemplazando `async_engine_from_config(...)` por:

   ```python
   from sqlalchemy.ext.asyncio import create_async_engine
   from app.core.database import build_engine_kwargs, build_url

   connectable = create_async_engine(
       build_url(), poolclass=pool.NullPool, connect_args=build_engine_kwargs()["connect_args"]
   )
   ```

   `target_metadata = None` está bien: el proyecto no declara modelos ORM, así que no hay
   `--autogenerate`. Las migraciones se escriben a mano (`op.execute("CREATE TABLE ...")`,
   `op.create_table(...)`).

4. Crear y aplicar migraciones:

   ```bash
   uv run alembic revision -m "add posts table"
   uv run alembic upgrade head
   ```

5. Si las migraciones corren dentro del contenedor, quitar `alembic.ini` de `.dockerignore`.
   Correrlas **una sola vez** por despliegue (job/servicio aparte), no en el arranque de cada réplica.

Elegir un solo mecanismo por proyecto: scripts en `database/init/` **o** Alembic, no ambos para
las mismas tablas.
