# Guía de Despliegue

Conceptos y configuración de producción, válidos con o sin Docker. Para el paso a paso con Docker Compose + Nginx + MariaDB ver [docker-deployment.md](docker-deployment.md).

---

## 1. Configuración de Producción

```bash
cp .env.example .env
```

| Variable | Valor en producción |
|---|---|
| `APP_ENV` | `production` (obligatoria) |
| `SECRET_KEY` | Reservado para la auth del proyecto. 32+ caracteres: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DB_PASS` | Contraseña fuerte (vacía o débil = la app no arranca) |
| `ENCRYPTION_KEYS` | Obligatoria en staging y producción. `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guardarla y respaldarla **aparte** del backup de la BD: sin ella no se descifran datos ni contraseñas |
| `ENCODING_ALPHABET` | Propio del proyecto y **fijo para siempre** (cambiarlo invalida los IDs ya compartidos). `uv run python -c "import random, string; a = list(string.ascii_letters + string.digits); random.shuffle(a); print(''.join(a))"` |
| `CORS_ORIGINS` | Dominios exactos: `https://app.com,https://admin.app.com` (`*` prohibido) |
| `DOCS_ENABLED` | Vacío = deshabilitadas en producción. Si se habilitan, usar `DOCS_PASSWORD_ENABLED=True` y `DOCS_PASSWORD` de 12+ caracteres (obligatorio en staging y producción) |
| `LOG_FORMAT` | `json` si hay agregador de logs |
| `LOGGER_MIDDLEWARE_ERRORS_ONLY` | `True` para registrar solo requests con error |
| `WORKERS` | Workers de uvicorn (lo lee el entrypoint / el comando de uvicorn, no la app) |
| `RATE_LIMIT_REDIS_ENABLED` | `True` si `WORKERS > 1` o hay varias réplicas |

La configuración se valida al arrancar (`app/core/environment.py`): si algo es inválido o inseguro, el proceso termina con `Configuración inválida: ...` (lista las variables por nombre, nunca sus valores) en lugar de arrancar mal. Los problemas no fatales (docs públicas en producción, `SECRET_KEY` vacío, variables desconocidas en el `.env`) se registran como warnings al iniciar; el aviso de rate limit en memoria con varios workers lo imprime el entrypoint de Docker.

---

## 2. Proceso: uvicorn

`docker/scripts/entrypoint.sh serve` ejecuta:

```bash
uvicorn main:app \
    --host 0.0.0.0 --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --timeout-graceful-shutdown "${GRACEFUL_TIMEOUT:-8}" \
    --no-access-log --no-server-header
```

El script también funciona fuera de Docker (necesita `uvicorn` en el `PATH`, ej. `.venv/bin`).

### IP real del cliente (`FORWARDED_ALLOW_IPS`)

El rate limit y los logs usan la IP del cliente. Detrás de un proxy, uvicorn solo acepta `X-Forwarded-For` de las IPs listadas en `--forwarded-allow-ips`:

- Solo la IP o red del proxy (`127.0.0.1` en bare-metal, `172.28.0.0/24` en el compose).
- **Nunca `*`**: cualquier cliente podría falsificar su IP y saltarse el rate limit.
- El proxy de borde debe **reemplazar** el header, no concatenarlo: nginx usa `X-Forwarded-For $remote_addr` (no `$proxy_add_x_forwarded_for`).

### Workers y pool de conexiones

Cada worker es un proceso con su propio pool. Regla:

```
WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW) × réplicas  <  max_connections del servidor
```

Con los defaults (10 + 10) y 2 workers son hasta 40 conexiones por réplica; el compose configura MariaDB con `--max-connections=300`.

- `DB_POOL_TIMEOUT=3`: con el pool agotado se responde 503 rápido en lugar de congelar el worker.
- `DB_POOL_RECYCLE` debe ser menor que `wait_timeout` del servidor (el compose usa `--wait-timeout=600`).
- `DB_STATEMENT_TIMEOUT` corta sentencias largas en el servidor (504).

### Apagado ordenado

Al recibir `SIGTERM`, uvicorn deja de aceptar conexiones, espera hasta `GRACEFUL_TIMEOUT` segundos a las requests en curso y ejecuta el lifespan de cierre (cliente HTTP → pool de la BD). `GRACEFUL_TIMEOUT` debe ser **menor** que el tiempo que el orquestador espera antes de `SIGKILL` (`stop_grace_period` en compose, `TimeoutStopSec` en systemd, `terminationGracePeriodSeconds` en Kubernetes).

### Rate limit con varios procesos

En memoria, cada worker cuenta por separado (el límite efectivo se multiplica). Opciones:

- `RATE_LIMIT_REDIS_ENABLED=True` + `RATE_LIMIT_REDIS_URL` (instalar con `uv sync --extra redis`; en Docker, `--build-arg UV_EXTRAS="--extra redis"`). Si Redis falla o está mal configurado, las requests pasan (fail-open) y se registra un warning.
- `limit_req` de nginx (ya configurado: 20 r/s por IP, burst 40), compartido entre todos los workers. Es el freno duro: el rate limit de la app es una dependencia y FastAPI la resuelve después de recibir el body.

---

## 3. Esquema de la Base de Datos

El esquema es SQL plano en `database/` (no se usa ORM ni Alembic) y la API **no** lo modifica al arrancar:

- Instalación nueva: aplicar `database/init/*.sql` en orden. Con Docker Compose, MariaDB los ejecuta solo al crear el volumen vacío.
- Cambios posteriores: un script nuevo numerado (`002_add_posts.sql`...) aplicado **una vez** por despliegue, antes de levantar la nueva versión, a mano o por el DBA:

  ```bash
  mariadb -h <host> -u <user> -p <db> < database/init/002_add_posts.sql
  ```

Hacer backup antes de aplicar cambios de esquema. Ver [database/README.md](../database/README.md).

---

## 4. Health Checks

| Endpoint | Tipo | Comportamiento |
|---|---|---|
| `GET /health` | Liveness | No toca dependencias. `200 {"status": "ok", "service": "<APP_NAME>"}` mientras el proceso atienda |
| `GET /ready` | Readiness | `SELECT 1` con timeout de 2 s. `200` con BD arriba, `503 {"status": "unavailable", "checks": {"database": "down"}}` si no (y un warning en el log con la causa) |

- Usar `/health` para reiniciar el contenedor/proceso y `/ready` para sacarlo del balanceo. Así una caída de la BD no provoca un bucle de reinicios.
- Si la BD no responde al arrancar, la app inicia igual y `/ready` lo reporta.
- Ninguno de los dos pasa por el log de requests (ni tiene `rate_limit()` propio). nginx sí les aplica `limit_req` (`burst=20`) para que `/ready` no sirva para martillar la BD.

---

## 5. Observabilidad

- **Logs**: `LOG_FORMAT=json` para Loki/ELK/Datadog. Cada línea lleva `request_id`.
- **Request ID**: se acepta un `X-Request-ID` entrante válido (nginx envía `$request_id`) o se genera uno; siempre vuelve en la respuesta. La misma request se correlaciona entre el log de nginx (`rid=`) y el de la app.
- **Event loop**: si hay latencias sin explicación, diagnosticar bloqueos con `py-spy dump --pid <pid>` (ver [Detectar bloqueos del event loop](development/best-practices.md#detectar-bloqueos-del-event-loop)).
- **OpenTelemetry**: telemetría nativa de FastAPI (`OTEL_ENABLED=True`). Solo exporta si se define `OTEL_EXPORTER_OTLP_ENDPOINT` (ej. `http://otel-collector:4318`). `/health` y `/ready` se excluyen.

---

## 6. Servidor Linux sin Docker (systemd)

### Instalación

```bash
sudo apt update && sudo apt install -y nginx mariadb-server git
curl -LsSf https://astral.sh/uv/install.sh | sh

sudo useradd --system --create-home --home-dir /opt/myapp --shell /usr/sbin/nologin app
sudo -u app git clone <tu-repositorio> /opt/myapp/src
cd /opt/myapp/src
sudo -u app uv sync --frozen --no-dev
sudo -u app cp .env.example .env    # editar: APP_ENV=production, SECRET_KEY, DB_*...
```

### Base de datos

```sql
CREATE DATABASE app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'app'@'localhost' IDENTIFIED BY '<contraseña_fuerte>';
GRANT ALL PRIVILEGES ON app.* TO 'app'@'localhost';
FLUSH PRIVILEGES;
```

```bash
for f in database/init/*.sql; do mariadb -u app -p app < "$f"; done    # esquema inicial, en orden
```

### Servicio

```ini
# /etc/systemd/system/myapp.service
[Unit]
Description=FastAPI myapp
After=network.target mariadb.service

[Service]
User=app
Group=app
WorkingDirectory=/opt/myapp/src
Environment=PATH=/opt/myapp/src/.venv/bin:/usr/bin:/bin
Environment=WORKERS=2
Environment=FORWARDED_ALLOW_IPS=127.0.0.1
Environment=GRACEFUL_TIMEOUT=20
ExecStart=/opt/myapp/src/docker/scripts/entrypoint.sh serve
Restart=always
TimeoutStopSec=30
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now myapp
journalctl -u myapp -f
```

La app lee el resto de variables desde `/opt/myapp/src/.env`.

### Nginx

Reutilizar `docker/nginx/nginx.conf` y `docker/nginx/conf.d/app.conf`, cambiando el upstream a `server 127.0.0.1:8000;`. Puntos clave de esa configuración:

- `proxy_set_header X-Forwarded-For $remote_addr;` (anti IP spoofing)
- `proxy_set_header X-Request-ID $request_id;`
- `limit_req zone=api_per_ip burst=40 nodelay;` (zona de 20 r/s por IP)
- `location ~ ^/(health|ready)$` sin access log y con `limit_req ... burst=20`
- `client_max_body_size 10M` igual a `REQUEST_MAX_SIZE_MB`
- Timeouts de proxy de 60 s

HTTPS: `sudo certbot --nginx -d tudominio.com` o seguir los pasos de [docker-deployment.md](docker-deployment.md#https-con-lets-encrypt).

---

## 7. Backups

```bash
#!/bin/sh
# /opt/scripts/backup-db.sh
set -eu
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p /opt/backups
mariadb-dump --single-transaction -u app -p"$DB_PASS" app | gzip > "/opt/backups/app_$DATE.sql.gz"
find /opt/backups -name "app_*.sql.gz" -mtime +7 -delete
```

```bash
echo "0 2 * * * root DB_PASS='...' /opt/scripts/backup-db.sh" | sudo tee /etc/cron.d/db-backup
```

Con Docker ver [Backups en docker-deployment.md](docker-deployment.md#backups).

---

## 8. Checklist de Despliegue

- [ ] `APP_ENV=production`, `SECRET_KEY` de 32+ caracteres, `DB_PASS` fuerte
- [ ] `ENCRYPTION_KEYS` definida y respaldada fuera de la BD; `ENCODING_ALPHABET` propio (el mismo en todos los despliegues del proyecto)
- [ ] `SECRET_KEY`, `DB_PASS` y `ENCRYPTION_KEYS` distintos entre sí
- [ ] `CORS_ORIGINS` con dominios exactos
- [ ] Docs deshabilitadas o protegidas con `DOCS_PASSWORD_ENABLED=True`
- [ ] `FORWARDED_ALLOW_IPS` = IP/red del proxy (nunca `*`)
- [ ] `GRACEFUL_TIMEOUT` < grace period del orquestador
- [ ] `WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW) × réplicas` < `max_connections`
- [ ] Rate limit en Redis si hay varios workers/réplicas (o confiar en `limit_req` de nginx)
- [ ] `REQUEST_MAX_SIZE_MB` = `client_max_body_size` de nginx
- [ ] Scripts de esquema nuevos (`database/init/`) aplicados una sola vez por despliegue, con backup previo
- [ ] Liveness en `/health`, readiness en `/ready`
- [ ] HTTPS habilitado
- [ ] Logs JSON / agregador y, si aplica, `OTEL_EXPORTER_OTLP_ENDPOINT`
- [ ] Backups automáticos probados (restaurar al menos una vez)
