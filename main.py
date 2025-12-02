from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.middleware.LoggerMiddleware import LoggerMiddleware
from app.utils.environments import SECRET_KEY

app = FastAPI()
app.add_middleware(LoggerMiddleware)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.get("/test/ping", tags=["test"])
async def ping():
    return {"message": "pong!"}
