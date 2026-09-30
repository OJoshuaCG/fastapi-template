"""
Health checks en la app raíz (sin versión, sin rate limit, sin logging de requests).

- /health: liveness. No toca dependencias → la app viva no se reinicia si la BD cae.
- /ready:  readiness. Verifica la BD con timeout → 503 si no responde (sacar del balanceo).
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.database import DatabaseDep
from app.core.environment import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_READY_TIMEOUT_SECONDS = 2


@router.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/ready")
async def ready(db: DatabaseDep):
    try:
        async with asyncio.timeout(_READY_TIMEOUT_SECONDS):
            await db.ping()
    except Exception as e:
        logger.warning("ready | base de datos no disponible: %s", type(e).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "checks": {"database": "down"}},
        )
    return {"status": "ok", "checks": {"database": "up"}}
