# Guía de Despliegue

Esta guía cubre cómo desplegar la aplicación FastAPI en diferentes entornos de producción.

## Preparación para Producción

### 1. Variables de Entorno

Crear `.env` para producción:

```env
# Aplicación
APP_ENV=production
APP_NAME="Mi API"
SECRET_KEY=<generar_clave_secreta_fuerte>

# Base de Datos
DB_HOST=db.production.example.com
DB_USER=api_user
DB_PASS=<contraseña_segura>
DB_NAME=api_production
DB_PORT=3306

# Logging
LOGGER_LEVEL=WARNING
LOGGER_MIDDLEWARE_ENABLED=True
LOGGER_MIDDLEWARE_SHOW_HEADERS=False
LOGGER_EXCEPTIONS_ENABLED=True
```

**Generar SECRET_KEY segura:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Dependencias de Producción

```bash
# Sincronizar dependencias
uv sync --no-dev

# O instalar solo dependencias de producción
uv sync --frozen
```

### 3. Migraciones

```bash
# Aplicar todas las migraciones
uv run alembic upgrade head

# Verificar estado
uv run alembic current
```

### 4. Configuración de Uvicorn

**Archivo de configuración** (`gunicorn_conf.py`):

```python
import multiprocessing
import os

# Bind
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Workers
workers = int(os.getenv('WEB_CONCURRENCY', multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv('LOG_LEVEL', 'info')

# Timeouts
timeout = 120
keepalive = 5

# Restart workers after N requests (previene memory leaks)
max_requests = 1000
max_requests_jitter = 50
```

## Opciones de Despliegue

### Opción 1: Docker (Recomendado)

#### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.13-slim

WORKDIR /app

# Instalar uv
RUN pip install uv

# Copiar archivos de dependencias
COPY pyproject.toml uv.lock ./

# Instalar dependencias
RUN uv sync --no-dev --frozen

# Copiar código de aplicación
COPY . .

# Exponer puerto
EXPOSE 8000

# Comando de inicio
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

#### docker-compose.yml

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=production
      - DB_HOST=db
      - DB_USER=api_user
      - DB_PASS=secure_password
      - DB_NAME=api_db
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: mariadb:11
    environment:
      - MYSQL_ROOT_PASSWORD=root_password
      - MYSQL_DATABASE=api_db
      - MYSQL_USER=api_user
      - MYSQL_PASSWORD=secure_password
    volumes:
      - db_data:/var/lib/mysql
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - api
    restart: unless-stopped

volumes:
  db_data:
```

#### Construir y Ejecutar

```bash
# Construir imagen
docker build -t mi-api .

# Ejecutar contenedor
docker run -d \
  -p 8000:8000 \
  --env-file .env.production \
  --name mi-api \
  mi-api

# Con docker-compose
docker-compose up -d

# Ver logs
docker-compose logs -f api

# Ejecutar migraciones
docker-compose exec api uv run alembic upgrade head
```

### Opción 2: Servidor Linux (VPS)

#### 1. Instalar Dependencias

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Python 3.13
sudo apt install python3.13 python3.13-venv -y

# Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar nginx
sudo apt install nginx -y

# Instalar MySQL/MariaDB
sudo apt install mariadb-server -y
```

#### 2. Configurar Aplicación

```bash
# Crear usuario
sudo useradd -m -s /bin/bash api

# Clonar repositorio
sudo -u api git clone <repo-url> /home/api/app
cd /home/api/app

# Instalar dependencias
sudo -u api uv sync --no-dev

# Configurar .env
sudo -u api nano .env
```

#### 3. Systemd Service

Crear `/etc/systemd/system/api.service`:

```ini
[Unit]
Description=FastAPI Application
After=network.target

[Service]
Type=notify
User=api
Group=api
WorkingDirectory=/home/api/app
Environment="PATH=/home/api/.local/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/api/.local/bin/uv run gunicorn main:app -c gunicorn_conf.py

[Install]
WantedBy=multi-user.target
```

Habilitar y ejecutar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable api
sudo systemctl start api
sudo systemctl status api
```

#### 4. Nginx Reverse Proxy

Crear `/etc/nginx/sites-available/api`:

```nginx
upstream api_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.example.com;

    # Redirigir a HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    # SSL
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # Configuración SSL
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Headers de seguridad
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Proxy a API
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Limitar tamaño de uploads
    client_max_body_size 10M;
}
```

Habilitar sitio:

```bash
sudo ln -s /etc/nginx/sites-available/api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 5. SSL con Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d api.example.com
sudo certbot renew --dry-run
```

### Opción 3: Plataformas Cloud

#### Heroku

**Procfile:**

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 4
release: alembic upgrade head
```

**Despliegue:**

```bash
heroku create mi-api
heroku addons:create jawsdb:kitefin
git push heroku main
```

#### Railway

1. Conectar repositorio de GitHub
2. Agregar variables de entorno
3. Railway detecta automáticamente FastAPI

#### Render

1. Crear nuevo Web Service
2. Build Command: `uv sync`
3. Start Command: `uv run uvicorn main:app --host 0.0.0.0 --port $PORT --workers 4`

#### AWS (EC2)

Similar a VPS Linux, seguir pasos de "Opción 2".

#### Google Cloud Run

**Dockerfile optimizado:**

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install uv && uv sync --no-dev

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$PORT"]
```

**Despliegue:**

```bash
gcloud run deploy mi-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## Optimizaciones

### Gunicorn + Uvicorn Workers

```bash
# Instalar gunicorn
uv add gunicorn

# Ejecutar
uv run gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Caching con Redis

```bash
uv add redis aiocache
```

```python
from aiocache import Cache
from aiocache.serializers import JsonSerializer

cache = Cache(Cache.REDIS, endpoint="localhost", port=6379, serializer=JsonSerializer())

@cached(ttl=300, cache=cache)
async def get_expensive_data():
    # ...
    pass
```

### CDN para Estáticos

Si sirves archivos estáticos, usa CDN (CloudFlare, AWS CloudFront, etc.).

### Database Connection Pooling

Ya configurado en `app/core/database.py`:

```python
self.engine = create_engine(DB_URL,
    pool_size=10,           # Conexiones permanentes
    max_overflow=20,        # Conexiones adicionales temporales
    pool_recycle=180,       # Reciclar conexiones cada 3 min
    pool_pre_ping=True      # Validar antes de usar
)
```

## Monitoreo

### Logs

#### Logging a Archivo

```python
# app/core/logger.py
from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(
    'app.log',
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=5
)
logger.addHandler(file_handler)
```

#### Servicios de Logging

- **Sentry**: Tracking de errores
- **LogRocket**: Session replay + logs
- **Datadog**: APM + logs
- **Papertrail**: Agregación de logs

**Sentry:**

```bash
uv add sentry-sdk[fastapi]
```

```python
# main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

if APP_ENV == "production":
    sentry_sdk.init(
        dsn="your-sentry-dsn",
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
    )
```

### Métricas

#### Prometheus

```bash
uv add prometheus-client
```

```python
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('request_count', 'Total requests')
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Request latency')

@app.middleware("http")
async def metrics_middleware(request, call_next):
    REQUEST_COUNT.inc()
    with REQUEST_LATENCY.time():
        response = await call_next(request)
    return response

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### Health Checks

```python
@app.get("/health")
async def health():
    # Verificar BD
    try:
        db.execute_query("SELECT 1", fetchone=True)
        db_status = "ok"
    except:
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status
    }
```

## Seguridad

### HTTPS

- **Producción**: Siempre usar HTTPS
- **Let's Encrypt**: Certificados SSL gratuitos
- **Nginx**: Configurar SSL correctamente

### Headers de Seguridad

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

if APP_ENV == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com"])
```

### CORS

```python
from fastapi.middleware.cors import CORSMiddleware

origins = ["https://miapp.com"]  # Solo dominios permitidos

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### Rate Limiting

```bash
uv add slowapi
```

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/")
@limiter.limit("60/minute")
async def root(request: Request):
    return {"message": "Hello World"}
```

## Backups

### Base de Datos

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_NAME="api_production"

mysqldump -u root -p$DB_PASS $DB_NAME | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Mantener solo últimos 7 días
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

Agregar a crontab:

```bash
# Backup diario a las 2 AM
0 2 * * * /home/api/backup.sh
```

## Troubleshooting

### Logs de Aplicación

```bash
# Ver logs del servicio
sudo journalctl -u api -f

# Ver últimas 100 líneas
sudo journalctl -u api -n 100
```

### Reiniciar Servicios

```bash
# Reiniciar API
sudo systemctl restart api

# Reiniciar Nginx
sudo systemctl restart nginx

# Ver estado
sudo systemctl status api nginx
```

### Verificar Conexiones

```bash
# Ver conexiones a puerto 8000
sudo netstat -tulpn | grep 8000

# Ver procesos de la app
ps aux | grep uvicorn
```

## Checklist de Despliegue

- [ ] Variables de entorno configuradas
- [ ] SECRET_KEY generada de forma segura
- [ ] Base de datos configurada
- [ ] Migraciones aplicadas (`alembic upgrade head`)
- [ ] SSL/HTTPS configurado
- [ ] Nginx/Reverse proxy configurado
- [ ] Logs configurados
- [ ] Monitoreo configurado (Sentry, etc.)
- [ ] Backups automáticos configurados
- [ ] Health check endpoint funcionando
- [ ] Rate limiting configurado
- [ ] CORS configurado correctamente
- [ ] Firewall configurado
- [ ] Dominio apuntando al servidor

## Recursos

- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt](https://letsencrypt.org/)

---

**¡Tu aplicación está lista para producción!**
