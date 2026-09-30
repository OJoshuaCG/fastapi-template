# Rate Limiting

El rate limit es una **dependencia** (`app/core/rate_limit.py`) basada en la librería `limits` (async, estrategia *moving window*). Hay dos niveles:

1. **Global por IP en nginx** (`limit_req`): corta tráfico abusivo antes de que llegue a Python, compartido entre workers y réplicas. La app no tiene un límite global propio.
2. **Por ruta en la app**: `rate_limit("5/minute")` en endpoints sensibles (login, registro, endpoints costosos).

> **Importante:** FastAPI resuelve las dependencias **después** de leer y parsear el body. El rate limit de la app responde 429, pero para entonces el body ya se recibió: no evita que un cliente envíe bodies grandes una y otra vez. El freno duro es `limit_req` de nginx (junto con `client_max_body_size` y `RequestSizeMiddleware`, que corta por tamaño).

## Configuración

```env
RATE_LIMIT_ENABLED=True
# Límite de ejemplo para login/registro. Formato: {n}/{second|minute|hour|day}
RATE_LIMIT_LOGIN=5/minute
# False = contadores en memoria de cada worker. True = Redis compartido (uv sync --extra redis)
RATE_LIMIT_REDIS_ENABLED=False
RATE_LIMIT_REDIS_URL=redis://localhost:6379
# Workers de uvicorn (lo lee el entrypoint de Docker, no la app)
WORKERS=1
```

`RATE_LIMIT_ENABLED=False` desactiva los límites de la app (la dependencia deja pasar todo). No afecta a nginx.

## Límite por ruta

```python
from app.core.rate_limit import rate_limit
from app.core.environment import settings


@router.post("/login", dependencies=[rate_limit(settings.RATE_LIMIT_LOGIN)])  # leído al importar
async def login(credentials: LoginSchema): ...


@router.post("/reports", dependencies=[rate_limit("10/hour")])
async def generate_report(...): ...
```

- Se suma al `limit_req` de nginx: la request tiene que pasar los dos.
- El endpoint **no** necesita un parámetro `request: Request`.
- Por defecto, el contador es por `MÉTODO:ruta` (plantilla con versión, ej. `POST:/api/v1/test/login`) y por IP: la misma ruta en v1 y v2 no comparte contador.

### Parámetros

```python
def rate_limit(
    limit: str,                                   # "5/minute", "100/hour", "10/second"
    *,
    scope: str | None = None,                     # agrupa el contador (default: método + ruta)
    key: Callable[[Request], str] = client_ip,    # identifica al cliente (default: IP)
)
```

Contador compartido entre varias rutas:

```python
auth_limit = rate_limit("10/minute", scope="auth")

@router.post("/login", dependencies=[auth_limit])
async def login(...): ...

@router.post("/password-reset", dependencies=[auth_limit])
async def password_reset(...): ...
```

Límite por API key en vez de IP:

```python
from fastapi import Request

from app.core.rate_limit import client_ip, rate_limit


def by_api_key(request: Request) -> str:
    return request.headers.get("X-Api-Key") or client_ip(request)


@router.get("/partners/items", dependencies=[rate_limit("1000/hour", key=by_api_key)])
async def partner_items(...): ...
```

## Respuesta 429

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
X-Request-ID: a1b2c3d4e5f6a7b8
```

```json
{
  "detail": {
    "msg": "Demasiadas solicitudes, intenta más tarde",
    "type": "TooManyRequests",
    "code": "rate_limited",
    "request_id": "a1b2c3d4e5f6a7b8"
  }
}
```

`Retry-After` (segundos) está expuesto por CORS para que el frontend lo lea. En development, `detail.context` incluye `limit` y `scope`.

## Storage: memoria vs Redis

| | Memoria (default) | Redis |
|---|---|---|
| Configuración | nada | `RATE_LIMIT_REDIS_ENABLED=True` + `uv sync --extra redis` (Docker: `--build-arg UV_EXTRAS="--extra redis"`) |
| Varios workers/réplicas | cada worker cuenta por separado (el límite efectivo se multiplica) | contador compartido |
| Reinicio | se pierden los contadores | persisten |

Con `WORKERS > 1` y storage en memoria el entrypoint de Docker imprime un aviso al arrancar. En ese caso, usa Redis o confía el límite duro a nginx.

`build_storage()` crea el storage: `async+memory://` o `async+<RATE_LIMIT_REDIS_URL>` con `implementation="redispy"` (`limits` usa coredis por defecto; el extra `redis` instala redis-py).

**Fail-open:** si Redis no responde o el storage está mal configurado (URL inválida, extra `redis` sin instalar), la request pasa y se registra un warning (`app.core.rate_limit`). El limitador no tumba la API.

## IP real detrás de un proxy

La clave por defecto es `request.client.host`. Detrás de nginx, uvicorn corre con `--proxy-headers --forwarded-allow-ips=<IP del proxy>` (`docker/scripts/entrypoint.sh`, variable `FORWARDED_ALLOW_IPS`, default `127.0.0.1`). Así `client.host` es la IP real del cliente.

- Nunca uses `--forwarded-allow-ips="*"`: cualquier cliente podría falsificar su IP con `X-Forwarded-For`.
- nginx reescribe `X-Forwarded-For` con `$remote_addr` (descarta el que manda el cliente).

## nginx

`docker/nginx/nginx.conf` y `docker/nginx/conf.d/app.conf`:

```nginx
limit_req_zone  $binary_remote_addr  zone=api_per_ip:10m  rate=20r/s;
limit_req_status 429;

location ~ ^/(health|ready)$ {
    limit_req  zone=api_per_ip burst=20 nodelay;   # /ready hace SELECT 1
    ...
}

location / {
    limit_req  zone=api_per_ip burst=40 nodelay;
    ...
}
```

`/health` y `/ready` también tienen `limit_req` (burst 20) para que `/ready` no sirva para martillar la BD. El 429 de nginx no tiene el formato JSON de la API.

## Tests

```python
from app.core.rate_limit import reset_rate_limits

await reset_rate_limits()  # limpia todos los contadores
```

`tests/conftest.py` lo ejecuta antes de cada test y usa `RATE_LIMIT_LOGIN=3/minute` para probar el 429 con pocas requests.

---

Ver también: [Manejo de Excepciones](exceptions.md) · [API Versionada](api-versioning.md)
