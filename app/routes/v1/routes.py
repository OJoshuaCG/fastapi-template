from fastapi import APIRouter

from app.core.environment import settings
from app.routes.v1 import test, users


def build_v1_router() -> APIRouter:
    router = APIRouter()
    router.include_router(users.router)

    # Endpoints de ejemplo/diagnóstico: nunca en producción
    if not settings.is_production:
        router.include_router(test.router)
    return router
