"""
Rate limiting como dependencia (librería `limits`, async).

- Límite global por IP: lo aplica nginx (limit_req), compartido entre workers y réplicas.
- Límite por ruta en la app (login, registro, endpoints costosos):

    from app.core.rate_limit import rate_limit

    @router.post("/login", dependencies=[rate_limit("5/minute")])
    async def login(...): ...

Storage en memoria por defecto (cada worker cuenta por separado). Con varios workers o
réplicas usar RATE_LIMIT_REDIS_ENABLED=True (uv sync --extra redis) o limit_req en nginx.
Si Redis falla, la request pasa (fail-open) y se loguea un warning.

La clave es la IP del cliente (request.client.host). Detrás de un proxy, uvicorn debe
correr con --proxy-headers y --forwarded-allow-ips=<IP del proxy> para que sea la IP real.
"""

import logging
import math
import time
from collections.abc import Callable
from typing import cast

from fastapi import Depends, Request
from limits import RateLimitItem, parse
from limits.aio.storage import Storage
from limits.aio.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string

from app.core.environment import settings
from app.exceptions.AppHttpException import AppHttpException
from app.utils.http import client_ip as scope_client_ip

logger = logging.getLogger(__name__)

_limiter: MovingWindowRateLimiter | None = None
_storage: Storage | None = None


def build_storage() -> Storage:
    """Memoria del proceso o Redis (cliente redis-py async, extra `redis`)."""
    if not settings.RATE_LIMIT_REDIS_ENABLED:
        storage = storage_from_string("async+memory://")
    else:
        # limits usa coredis por defecto: se fuerza redis-py, que es lo que instala el extra
        storage = storage_from_string(
            "async+" + settings.RATE_LIMIT_REDIS_URL.get_secret_value(), implementation="redispy"
        )
    # URI "async+..." → siempre un storage async
    return cast(Storage, storage)


def get_limiter() -> MovingWindowRateLimiter:
    global _limiter, _storage
    if _limiter is None:
        _storage = build_storage()
        _limiter = MovingWindowRateLimiter(_storage)
    return _limiter


async def reset_rate_limits() -> None:
    """Limpia todos los contadores (tests)."""
    get_limiter()
    if _storage is not None:
        await _storage.reset()


def client_ip(request: Request) -> str:
    return scope_client_ip(request.scope)


def rate_limit(
    limit: str,
    *,
    scope: str | None = None,
    key: Callable[[Request], str] = client_ip,
):
    """
    Dependencia que limita solicitudes. `limit`: "5/minute", "100/hour", "10/second".
    `scope`: agrupa el contador (default: la ruta). `key`: identifica al cliente (default: IP).
    """
    item: RateLimitItem = parse(limit)

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        route = request.scope.get("route")
        # Incluye root_path (/api/v1): la misma ruta en v1 y v2 no comparte contador
        route_path = getattr(route, "path", None)
        path = (
            f"{request.scope.get('root_path', '')}{route_path}" if route_path else request.url.path
        )
        identifier = scope or f"{request.method}:{path}"
        who = key(request)
        try:
            limiter = get_limiter()
            allowed = await limiter.hit(item, identifier, who)
            if allowed:
                return
            stats = await limiter.get_window_stats(item, identifier, who)
            retry_after = max(1, math.ceil(stats.reset_time - time.time()))
        except Exception as e:  # storage caído o mal configurado: no tumbar la API por el limitador
            logger.warning(
                "rate limit no disponible (%s): se permite la solicitud", type(e).__name__
            )
            return
        raise AppHttpException(
            "Demasiadas solicitudes, intenta más tarde",
            429,
            {"limit": limit, "scope": identifier},
            code="rate_limited",
            headers={"Retry-After": str(retry_after)},
        )

    return Depends(dependency)
