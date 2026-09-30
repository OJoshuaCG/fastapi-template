# File Upload

`app/utils/file_upload.py` guarda archivos subidos en disco sin bloquear el event loop:

- Copia en bloques de 1 MB con `anyio`, sin cargar el archivo completo en memoria.
- Valida el tamaño **mientras copia**. Al superar el límite aborta con 413 y elimina el archivo parcial.
- Genera un nombre único (`uuid4().hex` + extensión) y conserva la extensión solo si es segura (`.` + 1–10 alfanuméricos).
- `uploads/` es **temporal**: el archivo se elimina siempre después de procesarlo.

## `save_upload()`

```python
async def save_upload(
    file: UploadFile,
    allowed_types: list[str] | None = None,
    max_size_mb: float | None = None,      # default: REQUEST_MAX_SIZE_MB
    destination: Path | None = None,       # default: UPLOAD_DIR
) -> UploadInfo
```

Retorna un `UploadInfo` (TypedDict):

```python
{
    "filename": "3f2a…c9.png",          # nombre en disco
    "original_filename": "foto.png",
    "content_type": "image/png",
    "size_bytes": 204800,
    "size_mb": 0.1953,
    "path": "/app/uploads/3f2a…c9.png",
}
```

Errores (`AppHttpException`):

| Situación | Status | `code` |
|---|---|---|
| `content_type` fuera de `allowed_types` | 415 | `unsupported_file_type` |
| Archivo mayor a `max_size_mb` | 413 | `file_too_large` |

## Uso

```python
from typing import Annotated

import anyio
from fastapi import APIRouter, File, UploadFile

from app.utils.file_upload import save_upload
from app.utils.response import ApiResponse, success

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/avatar", response_model=ApiResponse[dict])
async def upload_avatar(file: Annotated[UploadFile, File()]):
    info = await save_upload(file, allowed_types=["image/jpeg", "image/png"], max_size_mb=2)
    path = anyio.Path(info["path"])
    try:
        content = await path.read_bytes()
        # procesar, subir a S3, etc.
        result = {"filename": info["original_filename"], "bytes": len(content)}
    finally:
        await path.unlink(missing_ok=True)  # SIEMPRE eliminar el temporal
    return success(data=result, message="Archivo procesado")
```

Usa `anyio.Path` (async) para leer y borrar, no `pathlib.Path.read_bytes()`, que bloquea el event loop con archivos grandes.

### Varios archivos

```python
from app.utils.file_upload import save_uploads


@router.post("/gallery", response_model=ApiResponse[list[dict]])
async def upload_gallery(files: Annotated[list[UploadFile], File()]):
    saved = await save_uploads(files, allowed_types=["image/jpeg", "image/png"], max_size_mb=5)
    results = []
    for info in saved:
        path = anyio.Path(info["path"])
        try:
            results.append({"filename": info["original_filename"], "size_mb": info["size_mb"]})
        finally:
            await path.unlink(missing_ok=True)
    return success(data=results)
```

Si un archivo falla (tipo o tamaño), `save_uploads` elimina los que ya había guardado y relanza el error.

### Procesamiento pesado

Las librerías síncronas o de CPU (PIL, pandas, openpyxl) se ejecutan en un thread para no bloquear el loop:

```python
from anyio import to_thread

thumbnail = await to_thread.run_sync(make_thumbnail, info["path"])
```

## Límites de tamaño

Hay tres límites en capas:

1. **nginx**: `client_max_body_size 10M` (`docker/nginx/nginx.conf`).
2. **`RequestSizeMiddleware`**: `REQUEST_MAX_SIZE_MB` (default 10) para **todo** el body de la request, antes de llegar al endpoint.
3. **`save_upload(max_size_mb=...)`**: límite por archivo.

`max_size_mb` no puede superar los dos primeros. No hay límites de body por ruta: para aceptar archivos más grandes, sube `REQUEST_MAX_SIZE_MB` y `client_max_body_size` de nginx (mantenerlos iguales) y acota cada endpoint con `max_size_mb`.

## Configuración

```env
# Carpeta temporal (relativa a la raíz del proyecto o absoluta)
UPLOAD_DIR=uploads
REQUEST_MAX_SIZE_MB=10
```

La carpeta se crea si no existe.

## Seguridad

- `content_type` **lo declara el cliente**. Si el tipo es crítico para la seguridad, valida el contenido real (magic bytes, o abrir la imagen con PIL).
- Nunca uses `original_filename` como ruta en disco. `save_upload` ya genera un nombre aleatorio.
- No sirvas `uploads/` como estático: es solo almacenamiento temporal de procesamiento.

---

Ver también: [Middlewares](middlewares.md#requestsizemiddleware)
