# Services e integraciones externas

`app/services/` contiene la lógica que **no pertenece a un solo controller**:

| Tipo | Ejemplo | Cómo |
|---|---|---|
| Negocio compartido (≥2 controllers) | cálculo de precios, reglas de inventario | clase que recibe models por constructor |
| Transversal | auditoría, notificaciones | clase que recibe models / otros services |
| Integración con una API externa | pagos, SMS, CRM | `class XService(ServiceClient)` |

Si solo un controller lo usa y no es una integración, va en el controller.

```
routes ──► controllers ──┬──► services (negocio) ──► models ──► MariaDB
                         └──► services (integración) ──► APIs externas
```

**Prohibido en un service**: `Request`/`Response`/`UploadFile`, importar controllers o routes, SQL directo
(va en models), crear `httpx.AsyncClient` propio, devolver `httpx.Response` (devolver `dict`, `list` o un
schema). `tests/test_architecture.py` lo verifica.

---

## Crear una integración externa

### 1. Credenciales (`app/core/environment.py` + `.env.example`)

Solo lo que es secreto o cambia por entorno, con prefijo por servicio:

```python
# ======= Servicio: Payments ======= #
PAYMENTS_TOKEN: SecretStr = SecretStr("")
```

La URL base **no** va al env por defecto: es parte del contrato con el proveedor y se fija en el
service. Solo si el proveedor tiene URLs distintas por entorno (sandbox/producción) se agrega
`PAYMENTS_BASE_URL` y se lee con una property (ver abajo).

### 2. Service (`app/services/payments_service.py`)

```python
from typing import Annotated, Any

from fastapi import Depends

from app.core.environment import settings
from app.core.http_client import ServiceClient


class PaymentsService(ServiceClient):
    name = "payments"                       # en logs y mensajes de error
    base_url = "https://api.payments.example/v1"
    timeout = 15                            # opcional (default HTTP_CLIENT_TIMEOUT)

    # Solo si la URL cambia entre entornos:
    # @property
    # def base_url(self) -> str:
    #     return settings.PAYMENTS_BASE_URL

    def headers(self) -> dict[str, str]:
        # Se lee en cada request: rotar el token no requiere reiniciar
        return {"Authorization": f"Bearer {settings.PAYMENTS_TOKEN.get_secret_value()}"}

    async def get_order(self, order_id: str) -> dict[str, Any]:
        return await self.get_json(f"/orders/{order_id}")

    async def find_order(self, order_id: str) -> dict[str, Any] | None:
        response = await self.request("GET", f"/orders/{order_id}", allow={404})
        return None if response.status_code == 404 else response.json()

    async def charge(self, order_id: str, amount: int, idempotency_key: str) -> dict[str, Any]:
        # POST no se reintenta por defecto; con idempotency key del proveedor sí es seguro
        return await self.post_json(
            "/charges",
            {"order_id": order_id, "amount": amount},
            headers={"Idempotency-Key": idempotency_key},
            retry=True,
        )


PaymentsServiceDep = Annotated[PaymentsService, Depends(PaymentsService.instance)]
```

### 3. Usarlo desde el controller

```python
class OrderController:
    def __init__(self, orders: OrderModel, payments: PaymentsService):
        self.orders = orders
        self.payments = payments

    async def pay(self, order_id: int, payload: PayIn) -> dict:
        order = await self.orders.find_by_id(order_id)          # 1. leer (conexión corta)
        charge = await self.payments.charge(...)                # 2. HTTP SIN transacción abierta
        await self.orders.mark_paid(order_id, charge["id"])     # 3. escribir
        return await self.orders.find_by_id(order_id)


def get_order_controller(orders: OrderModelDep, payments: PaymentsServiceDep) -> OrderController:
    return OrderController(orders, payments)
```

---

## Qué resuelve `ServiceClient`

| Tema | Comportamiento |
|---|---|
| Pool | Un `httpx.AsyncClient` **por servicio**, creado en el primer uso y reutilizado (`instance()`). Un proveedor lento no agota las conexiones de otro. Se cierra en el lifespan (`close_all()`). |
| Límites | `HTTP_CLIENT_MAX_CONNECTIONS` (20) por servicio, `keepalive_expiry=5s` (menor que el idle timeout típico de proveedores). |
| Timeouts | Total `HTTP_CLIENT_TIMEOUT` (10s, o `timeout` del service), conexión `HTTP_CLIENT_CONNECT_TIMEOUT` (5s), espera de pool `HTTP_CLIENT_POOL_TIMEOUT` (2s: fallar rápido). |
| Redirects | No se siguen (un 3xx inesperado es un 502). |
| Request ID | El `X-Request-ID` de la request entrante viaja al proveedor. |
| Reintentos | Solo GET/HEAD/OPTIONS/PUT/DELETE (o `retry=True`), ante error de conexión o 429/502/503/504; máx. `HTTP_CLIENT_MAX_RETRIES` (2) con backoff y jitter; respeta `Retry-After` ≤ 5s; nunca excede el timeout total. Un timeout de lectura **no** se reintenta (el proveedor pudo haber procesado la request). |
| Logs | Una línea por intento: `payments \| GET /orders/1 \| 200 \| 85ms \| intento 1`. Sin query string ni bodies. |

### Errores traducidos

| Situación | Status al cliente | `code` / `reason` |
|---|---|---|
| Pool del servicio lleno | 503 | `external_service_unavailable` / `pool_exhausted` |
| No conecta / conexión cortada | 503 | `external_service_unavailable` / `connection_error` |
| Timeout | 504 | `external_service_timeout` / `timeout` |
| Proveedor 429 o 503 | 503 (+ su `Retry-After`) | `external_service_unavailable` / `upstream_429` |
| Proveedor 401/403 | **502** | `external_service_error` / `upstream_auth` |
| Otro 4xx/5xx, redirect | 502 | `external_service_error` / `upstream_<status>` |
| JSON inválido | 502 | `external_service_error` / `invalid_json` |

Un 401 del proveedor significa que **nuestras** credenciales fallan: reenviarlo como 401 haría que el
frontend cierre la sesión del usuario. `context` (solo visible en development) lleva servicio, método, URL
sin query y status; el body del proveedor solo en development.

Para manejar un status concreto como negocio, usar `allow={...}` y decidir en el service.

---

## Tests (sin red)

```python
import httpx

def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/orders/1"
    return httpx.Response(200, json={"id": "1"})

service = PaymentsService(transport=httpx.MockTransport(handler))
assert await service.get_order("1") == {"id": "1"}

# En un endpoint:
v1_app.dependency_overrides[PaymentsService.instance] = lambda: service
```

Ver `tests/test_http_client.py` (reintentos, traducción de errores, secretos fuera de los logs).

## Prohibido

- `httpx.AsyncClient(...)` fuera de `app/core/http_client.py`, `requests`, `urllib`.
- Llamar a un servicio externo con una transacción de BD abierta.
- Reenviar al cliente el status o el body del proveedor.
- Tokens en la query string si el proveedor acepta headers (las URLs terminan en logs de proxies).
- Reintentar POST/PATCH sin idempotency key.
