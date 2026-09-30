"""
Guardado de archivos subidos (async, por bloques).

- El archivo se copia a disco en bloques de 1 MB con anyio (sin bloquear el event loop
  y sin cargar el archivo completo en memoria).
- El tamaño se valida mientras se copia: al superar el límite se aborta con 413 y se
  elimina el archivo parcial.
- `uploads/` es temporal: después de procesar, SIEMPRE eliminar el archivo (ver ejemplo).

Uso:
    info = await save_upload(file, allowed_types=["image/png"], max_size_mb=2)
    path = anyio.Path(info["path"])
    try:
        content = await path.read_bytes()
        ...
    finally:
        await path.unlink(missing_ok=True)
"""

import re
import uuid
from pathlib import Path
from typing import TypedDict

import anyio
from fastapi import UploadFile

from app.core.environment import settings
from app.exceptions.AppHttpException import AppHttpException

_CHUNK_SIZE = 1024 * 1024
_SAFE_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


class UploadInfo(TypedDict):
    filename: str
    original_filename: str
    content_type: str | None
    size_bytes: int
    size_mb: float
    path: str


async def save_upload(
    file: UploadFile,
    allowed_types: list[str] | None = None,
    max_size_mb: float | None = None,
    destination: Path | None = None,
) -> UploadInfo:
    """
    Guarda un archivo subido y retorna su metadata.

    Args:
        allowed_types: MIME types permitidos (el cliente los declara: validar el contenido
                       si el tipo es crítico para la seguridad).
        max_size_mb:   límite del archivo; por defecto REQUEST_MAX_SIZE_MB.
        destination:   carpeta destino; por defecto UPLOAD_DIR.

    Raises:
        AppHttpException 415 tipo no permitido · 413 archivo demasiado grande.
    """
    if allowed_types and file.content_type not in allowed_types:
        raise AppHttpException(
            f"Tipo de archivo no permitido: {file.content_type}",
            415,
            {"allowed_types": allowed_types, "received_type": file.content_type},
            code="unsupported_file_type",
        )

    limit_mb = max_size_mb if max_size_mb is not None else settings.REQUEST_MAX_SIZE_MB
    max_bytes = int(limit_mb * 1024 * 1024)
    if file.size is not None and file.size > max_bytes:
        raise _too_large(limit_mb)

    upload_dir = anyio.Path(destination or settings.UPLOAD_DIR)
    await upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "file"
    extension = Path(original_name).suffix
    if not _SAFE_EXTENSION.fullmatch(extension):
        extension = ""
    unique_name = f"{uuid.uuid4().hex}{extension}"
    target = upload_dir / unique_name

    size = 0
    try:
        async with await anyio.open_file(target, "wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise _too_large(limit_mb)
                await out.write(chunk)
    except BaseException:
        await target.unlink(missing_ok=True)
        raise

    return {
        "filename": unique_name,
        "original_filename": original_name,
        "content_type": file.content_type,
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 4),
        "path": str(target),
    }


async def save_uploads(
    files: list[UploadFile],
    allowed_types: list[str] | None = None,
    max_size_mb: float | None = None,
    destination: Path | None = None,
) -> list[UploadInfo]:
    """Varios archivos. Si uno falla, se eliminan los ya guardados y se relanza el error."""
    saved: list[UploadInfo] = []
    try:
        for file in files:
            saved.append(await save_upload(file, allowed_types, max_size_mb, destination))
    except BaseException:
        for info in saved:
            await anyio.Path(info["path"]).unlink(missing_ok=True)
        raise
    return saved


def _too_large(limit_mb: float) -> AppHttpException:
    return AppHttpException(
        f"Archivo demasiado grande. Máximo permitido: {limit_mb}MB",
        413,
        {"max_mb": limit_mb},
        code="file_too_large",
    )
