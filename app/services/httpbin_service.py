"""
EJEMPLO de integración externa (https://httpbin.org). Borrar al iniciar el proyecto.

Receta para una API nueva (ver docs/features/services.md):
    1. Clase que hereda de ServiceClient con `name` y `base_url` (fija en el código) y métodos
       de negocio que devuelven dict/list/modelos (nunca httpx.Response).
    2. Credenciales como settings <NAME>_TOKEN (SecretStr) en app/core/environment.py y
       .env.example, leídas en headers().
    3. `<Name>ServiceDep` para inyectarlo en el controller (o en la route si no hay controller).
"""

from typing import Annotated, Any

from fastapi import Depends

from app.core.http_client import ServiceClient


class HttpbinService(ServiceClient):
    name = "httpbin"
    base_url = "https://httpbin.org"

    # Si el proveedor requiere credenciales (settings.<NAME>_TOKEN):
    # def headers(self) -> dict[str, str]:
    #     return {"Authorization": f"Bearer {settings.HTTPBIN_TOKEN.get_secret_value()}"}

    async def echo(self, params: dict[str, str]) -> dict[str, Any]:
        """GET /get: devuelve los query params y headers recibidos.

        httpbin.org (detrás de AWS) descarta X-Request-ID; un httpbin local
        (docker run -p 8080:80 kennethreitz/httpbin) sí lo devuelve.
        """
        data = await self.get_json("/get", params=params)
        headers = {k.lower(): v for k, v in data.get("headers", {}).items()}
        return {"args": data.get("args", {}), "request_id": headers.get("x-request-id")}

    async def status(self, code: int) -> int:
        """GET /status/{code}: responde con ese status (prueba la traducción de errores)."""
        response = await self.request("GET", f"/status/{code}")
        return response.status_code


HttpbinServiceDep = Annotated[HttpbinService, Depends(HttpbinService.instance)]
