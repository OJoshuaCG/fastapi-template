from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.exceptions import (
    AppHttpException,
    app_exception_handler,
    generic_exception_handler,
)
from app.middleware.LoggerMiddleware import LoggerMiddleware
from app.routes.test import router as test_router
from app.utils.environments import SECRET_KEY

app = FastAPI()

# === Middlewares
app.add_middleware(LoggerMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# === Exceptions
app.add_exception_handler(AppHttpException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# === Routes
app.include_router(test_router)
