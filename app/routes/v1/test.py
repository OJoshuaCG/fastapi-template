"""
Endpoints de ejemplo (solo fuera de producción, ver routes.py).
"""

import asyncio
from typing import Annotated

import anyio
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.core.environment import settings
from app.core.rate_limit import rate_limit
from app.exceptions import AppHttpException
from app.services.httpbin_service import HttpbinServiceDep
from app.utils.file_upload import save_upload, save_uploads
from app.utils.pagination import PaginationDep
from app.utils.response import ApiResponse, empty, paginated, success

router = APIRouter(tags=["test"], prefix="/test")

# ---------------------------------------------------------------------------
# Envelope estándar de respuesta
# ---------------------------------------------------------------------------


@router.get("/ping", response_model=ApiResponse[dict])
async def ping():
    return success(data={"message": "pong!"})


@router.get("/paginated", response_model=ApiResponse[list[dict]])
async def paginated_example(pagination: PaginationDep):
    items = [{"id": i, "name": f"Item {i}"} for i in range(1, 51)]
    page = items[pagination.offset : pagination.offset + pagination.size]
    return paginated(page, total=len(items), pagination=pagination)


@router.delete("/resource/{resource_id}", response_model=ApiResponse[None])
async def delete_example(resource_id: int):
    return empty(f"Recurso {resource_id} eliminado exitosamente")


# ---------------------------------------------------------------------------
# Errores (formato `detail` independiente del envelope)
# ---------------------------------------------------------------------------


@router.put("/custom-error")
async def custom_error():
    raise AppHttpException(
        "Error de ejemplo", 400, {"hint": "visible solo en development"}, code="example"
    )


@router.post("/unhandled-error")
async def unhandled_error():
    raise RuntimeError("Error no controlado de ejemplo")


# ---------------------------------------------------------------------------
# Rate limit por ruta (además del límite global de la versión)
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=ApiResponse[dict],
    dependencies=[rate_limit(settings.RATE_LIMIT_LOGIN)],  # leído al importar
)
async def login_example():
    return success(data={"token": "fake"}, message="Ejemplo: límite estricto por IP")


# ---------------------------------------------------------------------------
# Servicio externo (ServiceClient): en un proyecto real lo llama el controller
# ---------------------------------------------------------------------------


@router.get("/external/echo", response_model=ApiResponse[dict])
async def external_echo(httpbin: HttpbinServiceDep, q: str = "hola"):
    """El X-Request-ID de esta request viaja al servicio externo."""
    return success(data=await httpbin.echo({"q": q}))


@router.get("/external/status/{code}", response_model=ApiResponse[dict])
async def external_status(code: int, httpbin: HttpbinServiceDep):
    """Probar la traducción: 500 → 502, 503 → 503, 401 → 502 (nunca se reenvía el 401)."""
    return success(data={"status": await httpbin.status(code)})


# ---------------------------------------------------------------------------
# Streaming (los middlewares ASGI puros no bufferean la respuesta)
# ---------------------------------------------------------------------------


@router.get("/stream")
async def stream_example():
    async def chunks():
        for i in range(3):
            yield f"chunk {i}\n"
            await asyncio.sleep(0)

    return StreamingResponse(chunks(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=ApiResponse[dict])
async def upload_single(file: Annotated[UploadFile, File()]):
    """save_upload() guarda en uploads/ → se procesa → se elimina SIEMPRE en finally."""
    info = await save_upload(
        file,
        allowed_types=["image/jpeg", "image/png", "image/webp", "text/plain"],
        max_size_mb=5,
    )
    path = anyio.Path(info["path"])
    try:
        content = await path.read_bytes()  # aquí: subir a S3, procesar, etc.
        result = {**info, "bytes_read": len(content)}
    finally:
        await path.unlink(missing_ok=True)
    return success(data=result, message="Archivo procesado y eliminado")


@router.post("/upload/multiple", response_model=ApiResponse[list[dict]])
async def upload_multiple(files: Annotated[list[UploadFile], File()]):
    saved = await save_uploads(
        files, allowed_types=["image/jpeg", "image/png", "image/webp"], max_size_mb=5
    )
    results = []
    for info in saved:
        path = anyio.Path(info["path"])
        try:
            content = await path.read_bytes()
            results.append({**info, "bytes_read": len(content)})
        finally:
            await path.unlink(missing_ok=True)
    return success(data=results, message=f"{len(results)} archivo(s) procesado(s)")
