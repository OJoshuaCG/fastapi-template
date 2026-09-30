# Despliegue con Docker Compose

Docker + Nginx + MariaDB en un VPS. Los conceptos generales (workers, pool, proxy, health checks) están en [deployment.md](deployment.md).

---

## Servicios

| Servicio | Imagen | Rol |
|---|---|---|
| `db` | `mariadb:11` | Base de datos (red `backend`, volumen `mariadb_data`). Root con contraseña aleatoria (`MARIADB_RANDOM_ROOT_PASSWORD`); `--collation-server=${DB_COLLATION:-utf8mb4_unicode_ci}` |
| `api` | build local | FastAPI + uvicorn (redes `backend` y `frontend`) |
| `nginx` | `nginx:alpine` | Reverse proxy, rate limit por IP, gzip, HTTPS (puertos 80/443) |

Orden de arranque:

```
db (healthy) → api (healthy) → nginx
```

La base arranca **vacía**: el compose no ejecuta scripts de esquema y la API no lo modifica. Aplicar `database/init/*.sql` y luego `database/procedures/*.sql` con el gestor de BD o el cliente `mariadb` usando `DB_USER`/`DB_PASS` (ver [Operación](#operación) y [database/README.md](../database/README.md)). El servidor arranca con `--character-set-server=utf8mb4 --collation-server=${DB_COLLATION}`, así la base creada coincide con la collation de la sesión de la app.

La API no está publicada al host (`expose: 8000`): solo nginx la alcanza por la red `frontend` (subred fija `172.28.0.0/24`).

---

## Imagen (`Dockerfile`)

- **Multi-stage**: `builder` instala dependencias con uv (versión fija `0.12.5`, `uv sync --frozen --no-dev`); `production` copia solo `/app` con su `.venv`. La imagen final no tiene uv ni curl.
- **Usuario sin privilegios** `app` (uid/gid 1000). El código y el `.venv` son de root (no escribibles en runtime); solo `/app/uploads` pertenece a `app`.
- **Healthcheck en Python puro** contra `http://127.0.0.1:$PORT/health` (cada 30 s, `start-period` 30 s).
- **Extras opcionales**: `docker build --build-arg UV_EXTRAS="--extra redis" .`
- `.dockerignore` excluye `.env`, tests, docs, `database/`, archivos de compose y `alembic.ini` (Alembic es opcional; quitarlo de `.dockerignore` si se usan migraciones en el contenedor): los secretos nunca entran a la imagen.

Variables por defecto de la imagen: `PORT=8000`, `WORKERS=1`, `GRACEFUL_TIMEOUT=8`, `FORWARDED_ALLOW_IPS=127.0.0.1`.

### Entrypoint (`docker/scripts/entrypoint.sh`)

| Comando | Qué hace |
|---|---|
| `serve` (default) | Inicia uvicorn |
| `<otro>` | Ejecuta el comando tal cual (`python -V`, `python -c ...`) |

uvicorn queda como PID 1 (`exec`) y recibe `SIGTERM` para el apagado ordenado. Si `WORKERS > 1` sin Redis, el entrypoint avisa que el rate limit en memoria cuenta por worker.

---

## Requisitos del VPS

- Linux con Docker Engine y el plugin Docker Compose v2 (el compose usa `env_file` con `required: false` y `depends_on` con `condition: service_healthy`)
- Puertos 80 y 443 abiertos

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
docker compose version
```

---

## 1. Clonar y configurar

```bash
git clone <tu-repositorio> /opt/myapp
cd /opt/myapp
cp .env.example .env
nano .env
```

Obligatorias en `.env`:

| Variable | Valor |
|---|---|
| `APP_ENV` | `production` |
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEYS` | `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (respaldar aparte de la BD) |
| `ENCODING_ALPHABET` | `uv run python -c "import random, string; a = list(string.ascii_letters + string.digits); random.shuffle(a); print(''.join(a))"` (fijo para siempre) |
| `DB_NAME`, `DB_USER`, `DB_PASS` | Base y usuario de la app (el contenedor MariaDB los crea; también para gestores de BD) |
| `CORS_ORIGINS` | `https://tudominio.com` |

El compose falla al iniciar si falta `DB_NAME`, `DB_USER` o `DB_PASS`. Root usa una contraseña aleatoria (`MARIADB_RANDOM_ROOT_PASSWORD`) y no se usa.

Fijados por `docker-compose.yml` (no hace falta ponerlos en `.env`):

| Servicio | Variable | Valor | Motivo |
|---|---|---|---|
| `api` | `DB_HOST` / `DB_PORT` | `db` / `3306` | Nombre del servicio en la red `backend` |
| `api` | `FORWARDED_ALLOW_IPS` | `172.28.0.0/24` | Solo nginx puede fijar la IP del cliente |
| `api` | `GRACEFUL_TIMEOUT` | `20` | Menor que `stop_grace_period: 30s` |

Opcionales relevantes: `WORKERS`, `RATE_LIMIT_REDIS_ENABLED` / `RATE_LIMIT_REDIS_URL` (requiere la imagen con `UV_EXTRAS="--extra redis"` y un Redis accesible), `LOG_FORMAT=json`.

---

## 2. Levantar

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api
docker compose logs db           # primer arranque: ejecución de database/init/*.sql
```

## 3. Verificar

```bash
curl -i http://localhost/health    # liveness
curl -i http://localhost/ready     # readiness: 503 si la BD no responde
```

Cada respuesta trae `X-Request-ID`; el mismo valor aparece como `rid=` en el log de nginx y como `request_id` en el de la app.

---

## Nginx

`docker/nginx/nginx.conf` + `docker/nginx/conf.d/app.conf`:

- Upstream `api:8000` con keepalive.
- **Anti IP spoofing**: `X-Forwarded-For $remote_addr` descarta el header que envíe el cliente. Combinado con `FORWARDED_ALLOW_IPS`, la IP que ve la app es la real.
- **Rate limit por IP**: zona `api_per_ip` de 20 r/s, `burst=40 nodelay`, responde 429. Compartido entre todos los workers; complementa el rate limit de la app.
- **Request ID**: `X-Request-ID $request_id` hacia la API.
- `/health` y `/ready` sin access log y con `limit_req` propio (`burst=20`), para que `/ready` (hace `SELECT 1`) no sirva para martillar la BD.
- `client_max_body_size 10M` (mantener igual a `REQUEST_MAX_SIZE_MB`).
- Timeouts de proxy de 60 s; headers de seguridad (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`); gzip; `server_tokens off`.

Recargar tras editar: `docker compose exec nginx nginx -s reload`.

---

## HTTPS con Let's Encrypt

1. Apuntar el dominio (registro `A`) a la IP del VPS.
2. Instalar Certbot en el host: `sudo apt install certbot -y`.
3. Con los servicios corriendo, obtener el certificado vía webroot (el volumen `certbot_www` está montado en `/var/www/certbot`):

   ```bash
   sudo certbot certonly --webroot \
     -w /var/lib/docker/volumes/$(basename $PWD)_certbot_www/_data \
     -d tudominio.com -d www.tudominio.com \
     --email tu@email.com --agree-tos --non-interactive
   ```

4. Los certificados deben quedar en el volumen `certbot_certs` (montado en `/etc/letsencrypt` del contenedor nginx). Si Certbot los escribe en `/etc/letsencrypt` del host, copiarlos al volumen o cambiar el montaje a un bind mount `/etc/letsencrypt:/etc/letsencrypt:ro`.
5. En `docker/nginx/conf.d/app.conf`: descomentar el bloque `server { listen 443 ssl ... }`, ajustar `server_name` y rutas de certificados, y en el bloque HTTP reemplazar `location /` por `return 301 https://$host$request_uri;`.
6. `docker compose exec nginx nginx -s reload`.

Renovación:

```bash
echo "0 */12 * * * root certbot renew --quiet --deploy-hook 'docker compose -f /opt/myapp/docker-compose.yml exec nginx nginx -s reload'" \
  | sudo tee /etc/cron.d/certbot-renew
```

---

## Operación

```bash
# Actualizar a una nueva versión
git pull
docker compose up -d --build

# Aplicar el esquema (BD recién creada: todos los scripts en orden) o un script nuevo
docker compose exec -T db sh -c 'mariadb -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < database/init/002_x.sql
# Stored procedure nuevo o modificado
docker compose exec -T db sh -c 'mariadb -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < database/procedures/sp_x.sql

# Shell y BD
docker compose exec api sh
docker compose exec db sh -c 'mariadb -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"'

# Reiniciar / detener
docker compose restart api
docker compose down          # conserva volúmenes
docker compose down -v       # ¡BORRA los datos!
```

### Varios workers

Definir `WORKERS` en `.env` y respetar `WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW) < 300` (`--max-connections` de `db`). Para que los límites por ruta de la app se compartan entre workers usar Redis; el límite global por IP es el `limit_req` de nginx, que no depende de los workers.

---

## Backups

```bash
#!/bin/sh
# /opt/scripts/backup-db.sh
set -eu
cd /opt/myapp
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p /opt/backups
docker compose exec -T db sh -c 'mariadb-dump --single-transaction --routines -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' \
  | gzip > "/opt/backups/backup_$DATE.sql.gz"
find /opt/backups -name "backup_*.sql.gz" -mtime +7 -delete
```

```bash
chmod +x /opt/scripts/backup-db.sh
echo "0 2 * * * root /opt/scripts/backup-db.sh" | sudo tee /etc/cron.d/db-backup
```

Restaurar:

```bash
gunzip -c backup_YYYYMMDD_HHMMSS.sql.gz | docker compose exec -T db sh -c 'mariadb -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"'
```

---

## Troubleshooting

### `api` no arranca / queda esperando

```bash
docker compose ps -a
docker compose logs db        # api espera a que db esté healthy (service_healthy)
docker compose logs api       # "Configuración inválida: ..." = revisar .env
```

### `/ready` responde 503

La API está viva pero no alcanza la BD: `docker compose logs db`, revisar `DB_*` en `.env`. Si se cambiaron credenciales después del primer arranque, MariaDB conserva las originales del volumen `mariadb_data`.

### `Table '...' doesn't exist`

El volumen `mariadb_data` ya existía, así que `database/init/` no se ejecutó (o falta un script nuevo). Aplicar el script a mano (ver Operación) o, solo en local, `docker compose down -v` para recrear el volumen.

### Nginx devuelve 502

`api` no está healthy o no escucha: `docker compose ps`, `docker compose logs api`, `docker compose logs nginx`.

### Todas las requests comparten la misma IP en los logs / rate limit

`FORWARDED_ALLOW_IPS` no coincide con la red de nginx (`172.28.0.0/24`), o se cambió la subred de `frontend` sin actualizarlo.

### 429 inesperados

Revisar si viene de nginx (límite global por IP: 20 r/s, burst 40; sin formato JSON) o de la app (límite por ruta con `rate_limit()`, ej. login con `RATE_LIMIT_LOGIN`; body JSON con `code: "rate_limited"` y header `Retry-After`).

---

## Checklist

Ver [Checklist de Despliegue](deployment.md#8-checklist-de-despliegue).
