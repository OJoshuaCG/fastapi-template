from fastapi import APIRouter

from app.exceptions import AppHttpException

router = APIRouter(tags=["test"], prefix="/test")


@router.get("/ping")
async def ping():
    return {"message": "pong!"}


@router.post("/syntax-error")
async def syntax_error():
    if None > 0:
        return {"message": "Syntax error!"}
    return {"message": "No syntax error!"}


@router.put("/custom-error")
async def custom_error():
    raise AppHttpException("Custom error")
