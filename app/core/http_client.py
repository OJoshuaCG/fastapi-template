"""
Base para integraciones con APIs externas: `ServiceClient`.

Cada API externa es un service en `app/services/<name>_service.py` que hereda de ServiceClient
y expone métodos de negocio (`get_order(id) -> dict`), nunca `httpx.Response`:

    class PaymentsService(ServiceClient):
        name = "payments"
        base_url = "https://api.payments.example/v1"   # fija en el código

        def headers(self) -> dict[str, str]:            # por request: credenciales rotables
            return {"Authorization": f"Bearer {settings.PAYMENTS_TOKEN.get_secret_value()}"}

        async def get_order(self, order_id: str) -> dict:
            return await self.get_json(f"/orders/{order_id}")

    PaymentsServiceDep = Annotated[PaymentsService, Depends(PaymentsService.instance)]

La URL base va en el código: es parte del contrato con el proveedor. Solo si cambia entre
entornos (sandbox/producción) se lee de una variable, con una property:

        @property
        def base_url(self) -> str:
            return settings.PAYMENTS_BASE_URL

Qué resuelve la base (no reimplementar en cada service):
- Un pool httpx POR SERVICIO, perezoso y reutilizado (un proveedor lento no agota el de otro);
  se cierra en el lifespan con close_all(). Nunca crear httpx.AsyncClient por request.
- Timeouts (conexión, total y espera de pool), sin seguir redirects, X-Request-ID propagado.
- Reintentos solo en métodos idempotentes (o retry=True) ante fallos transitorios, con backoff
  y Retry-After (máx. 5s), sin pasarse del timeout total.
- Errores traducidos a AppHttpException: 503 no disponible / 504 timeout / 502 respuesta
  inválida. Un 401/403 del proveedor NUNCA se reenvía como 401 al cliente (es un 502 nuestro).
- Logs por intento sin query string ni bodies (pueden llevar tokens o PII).

Tests: `PaymentsService(transport=httpx.MockTransport(handler))` y dependency_overrides.
"""

import asyncio
import logging
import random
import time
from typing import Any, ClassVar, Self

import httpx

from app.core.context import get_request_id
from app.core.environment import settings
from app.exceptions import AppHttpException

logger = logging.getLogger("app.http_client")

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
RETRY_STATUSES = frozenset({429, 502, 503, 504})
MAX_RETRY_AFTER = 5.0

_registry: dict[type["ServiceClient"], "ServiceClient"] = {}


class ServiceClient:
    """Cliente base de una API externa. Heredar, definir `name` y `base_url`."""

    name: ClassVar[str] = "external"
    base_url: ClassVar[str] = ""
    # None = settings.HTTP_CLIENT_TIMEOUT. Definir por service si el proveedor es más lento/rápido
    timeout: ClassVar[float | None] = None
    max_retries: ClassVar[int | None] = None

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    # ---- A definir por cada service -------------------------------------------------- #

    def headers(self) -> dict[str, str]:
        """Headers por request (se leen en cada llamada: un token rotado aplica sin reiniciar)."""
        return {}

    # ---- Ciclo de vida ---------------------------------------------------------------- #

    @classmethod
    def instance(cls) -> Self:
        """Instancia compartida por proceso (úsala como dependency: Depends(Svc.instance))."""
        existing = _registry.get(cls)
        if existing is None:
            existing = _registry[cls] = cls()
        return existing  # type: ignore[return-value]

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            if not self.base_url:
                raise NotImplementedError(f"{type(self).__name__} debe definir base_url")
            total = self.timeout or settings.HTTP_CLIENT_TIMEOUT
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    total,
                    connect=min(settings.HTTP_CLIENT_CONNECT_TIMEOUT, total),
                    pool=settings.HTTP_CLIENT_POOL_TIMEOUT,
                ),
                limits=httpx.Limits(
                    max_connections=settings.HTTP_CLIENT_MAX_CONNECTIONS,
                    max_keepalive_connections=settings.HTTP_CLIENT_MAX_CONNECTIONS,
                    # Menor que el idle timeout típico de proveedores/balanceadores (~60s):
                    # evita reutilizar conexiones que el otro lado ya cerró
                    keepalive_expiry=5,
                ),
                headers={"User-Agent": settings.APP_NAME},
                follow_redirects=False,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    # ---- Requests --------------------------------------------------------------------- #

    async def request(
        self,
        method: str,
        path: str,
        *,
        retry: bool | None = None,
        allow: frozenset[int] | set[int] = frozenset(),
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Request con reintentos y errores traducidos. Devuelve la respuesta 2xx (o en `allow`,
        ej. {404} para "no existe" sin excepción). `retry=True` fuerza reintentos en POST/PATCH
        (solo si el proveedor acepta idempotency keys); `retry=False` los desactiva.
        """
        method = method.upper()
        retries = (
            self.max_retries if self.max_retries is not None else settings.HTTP_CLIENT_MAX_RETRIES
        )
        if not (retry if retry is not None else method in IDEMPOTENT_METHODS):
            retries = 0
        deadline = time.monotonic() + (self.timeout or settings.HTTP_CLIENT_TIMEOUT)
        headers = {**self.headers(), **(kwargs.pop("headers", None) or {})}
        if rid := get_request_id():
            headers.setdefault("X-Request-ID", rid)

        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            error: httpx.HTTPError | None = None
            response: httpx.Response | None = None
            try:
                response = await self._http().request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                error = exc
            elapsed_ms = (time.monotonic() - started) * 1000
            self._log(method, path, response, error, attempt, elapsed_ms)

            if response is not None and (response.is_success or response.status_code in allow):
                return response

            wait = _retry_delay(response, error, attempt)
            if attempt > retries or wait is None or time.monotonic() + wait >= deadline:
                if response is not None:
                    await response.aread()
                raise translate_http_error(self.name, method, path, response=response, error=error)
            if response is not None:
                await response.aclose()
            await asyncio.sleep(wait)

    async def get_json(self, path: str, **kwargs: Any) -> Any:
        return _json(self.name, "GET", path, await self.request("GET", path, **kwargs))

    async def post_json(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        response = await self.request("POST", path, json=json, **kwargs)
        return _json(self.name, "POST", path, response)

    def _log(
        self,
        method: str,
        path: str,
        response: httpx.Response | None,
        error: httpx.HTTPError | None,
        attempt: int,
        elapsed_ms: float,
    ) -> None:
        outcome = str(response.status_code) if response is not None else type(error).__name__
        ok = response is not None and response.is_success
        logger.log(
            logging.INFO if ok else logging.WARNING,
            "%s | %s %s | %s | %.0fms | intento %s",
            self.name,
            method,
            redact_url(path),
            outcome,
            elapsed_ms,
            attempt,
        )


# ---------------------------------------------------------------------------------------- #


async def close_all() -> None:
    """Cierra los pools de todos los services (lifespan de main.py)."""
    services = list(_registry.values())
    _registry.clear()
    for service in services:
        await service.aclose()


def redact_url(url: str | httpx.URL) -> str:
    """URL sin query string ni credenciales (las API keys suelen viajar en la query)."""
    parsed = httpx.URL(str(url))
    return str(parsed.copy_with(query=None, fragment=None, userinfo=b""))


def _retry_delay(
    response: httpx.Response | None, error: httpx.HTTPError | None, attempt: int
) -> float | None:
    """Segundos a esperar antes de reintentar, o None si el fallo no es transitorio."""
    if error is not None:
        # Timeouts de lectura no se reintentan: el proveedor pudo haber procesado la request
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError)):
            return _backoff(attempt)
        return None
    if response is None or response.status_code not in RETRY_STATUSES:
        return None
    retry_after = _retry_after_seconds(response)
    if retry_after is not None:
        return retry_after if retry_after <= MAX_RETRY_AFTER else None
    return _backoff(attempt)


def _backoff(attempt: int) -> float:
    return min(0.2 * 2 ** (attempt - 1), 2.0) * random.uniform(0.5, 1.0)  # noqa: S311


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "")
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def translate_http_error(
    service: str,
    method: str,
    path: str,
    *,
    response: httpx.Response | None = None,
    error: httpx.HTTPError | None = None,
) -> AppHttpException:
    """Fallo de una API externa → AppHttpException (el cliente nunca ve el error crudo)."""
    context: dict[str, Any] = {"service": service, "method": method, "url": redact_url(path)}

    if response is None:
        context["error"] = type(error).__name__
        if isinstance(error, httpx.PoolTimeout):
            return _unavailable(service, "pool_exhausted", context)
        if isinstance(error, httpx.TimeoutException):
            return AppHttpException(
                f"El servicio {service} tardó demasiado en responder",
                504,
                context,
                code="external_service_timeout",
                reason="timeout",
            )
        return _unavailable(service, "connection_error", context)

    status = response.status_code
    context["status"] = status
    if settings.is_development:
        context["body"] = response.text[:500]
    if status in (429, 503):
        retry_after = response.headers.get("Retry-After")
        headers = {"Retry-After": retry_after} if retry_after and retry_after.isdigit() else None
        return _unavailable(service, f"upstream_{status}", context, headers=headers)
    return AppHttpException(
        f"El servicio {service} respondió con un error",
        502,
        context,
        code="external_service_error",
        # 401/403: credenciales NUESTRAS inválidas; nunca reenviarlo al cliente como 401
        reason="upstream_auth" if status in (401, 403) else f"upstream_{status}",
    )


def _unavailable(
    service: str, reason: str, context: dict[str, Any], headers: dict[str, str] | None = None
) -> AppHttpException:
    return AppHttpException(
        f"El servicio {service} no está disponible, intenta más tarde",
        503,
        context,
        code="external_service_unavailable",
        reason=reason,
        headers=headers,
    )


def _json(service: str, method: str, path: str, response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        context: dict[str, Any] = {
            "service": service,
            "method": method,
            "url": redact_url(path),
            "status": response.status_code,
        }
        if settings.is_development:
            context["body"] = response.text[:500]
        raise AppHttpException(
            f"El servicio {service} respondió con un formato inválido",
            502,
            context,
            code="external_service_error",
            reason="invalid_json",
        ) from None
