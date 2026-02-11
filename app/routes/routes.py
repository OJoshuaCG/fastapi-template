from fastapi import APIRouter

from . import test  # Import modules from the app/routes directory

router = APIRouter()

router.include_router(test.router)
