# Integraciones externas

Reglas para consumir APIs externas con `ServiceClient`. Léelo antes de crear o modificar un service de integración.

## Integraciones externas (`app/services/` + `ServiceClient`)

Cada API externa = un service. Ejemplo de referencia: `app/services/httpbin_service.py` (borrar al iniciar).

```python
# 1. app/core/environment.py + .env.example: PAYMENTS_TOKEN (SecretStr)
# 2. app/services/payments_service.py
class PaymentsService(ServiceClient):
    name = "payments"          # aparece en logs y en los mensajes de error
    base_url = "https://api.payments.example/v1"   # fija; property con settings solo si cambia por entorno
    timeout = 15               # opcional (default HTTP_CLIENT_TIMEOUT)

    def headers(self) -> dict[str, str]:       # por request: un token rotado aplica sin reiniciar
        return {"Authorization": f"Bearer {settings.PAYMENTS_TOKEN.get_secret_value()}"}

    async def get_order(self, order_id: str) -> dict:          # métodos de negocio, nunca httpx.Response
        return await self.get_json(f"/orders/{order_id}")

    async def find_order(self, order_id: str) -> dict | None:  # 404 esperado → None
        response = await self.request("GET", f"/orders/{order_id}", allow={404})
        return None if response.status_code == 404 else response.json()

PaymentsServiceDep = Annotated[PaymentsService, Depends(PaymentsService.instance)]

# 3. El controller lo recibe por constructor (get_x_controller(..., payments: PaymentsServiceDep))
```

La base ya resuelve (no reimplementar): pool httpx **por servicio** (perezoso, cerrado en el lifespan con
`close_all()`), timeouts de conexión/total/pool, sin seguir redirects, `X-Request-ID` propagado, reintentos
con backoff **solo** en GET/HEAD/OPTIONS/PUT/DELETE (`retry=True` para un POST con idempotency key),
`Retry-After` ≤ 5s, logs por intento sin query string ni bodies. Errores traducidos:

| Situación | Status | code / reason |
|---|---|---|
| Pool del servicio lleno | 503 | `external_service_unavailable` / `pool_exhausted` |
| No conecta / conexión cortada | 503 | `external_service_unavailable` / `connection_error` |
| Timeout | 504 | `external_service_timeout` / `timeout` |
| Proveedor responde 429/503 | 503 (+ su `Retry-After`) | `external_service_unavailable` / `upstream_429` o `upstream_503` |
| Proveedor responde 401/403 | 502 (**nunca** se reenvía el 401) | `external_service_error` / `upstream_auth` |
| Otro 4xx/5xx, redirect, JSON inválido | 502 | `external_service_error` / `upstream_<status>` / `invalid_json` |

**Prohibido**: `httpx.AsyncClient(...)` fuera de `core/http_client.py` (lo verifica `test_architecture.py`),
`requests`, llamar un servicio externo con una transacción de BD abierta, reenviar al cliente el status o body
del proveedor, poner tokens en la query string si el proveedor acepta headers.

Tests sin red: `PaymentsService(transport=httpx.MockTransport(handler))` y
`v1_app.dependency_overrides[PaymentsService.instance] = lambda: fake` (ver `tests/test_http_client.py`).

