from fastapi import FastAPI

from app.exceptions import (
    AppHttpException,
    app_exception_handler,
    generic_exception_handler,
)
from app.middleware.ContextMiddleware import ContextMiddleware
from app.middleware.LoggerMiddleware import LoggerMiddleware
from app.routes.routes import router as routes_router

app = FastAPI()

# === Middlewares
app.add_middleware(LoggerMiddleware)
app.add_middleware(ContextMiddleware)

# === Exceptions
app.add_exception_handler(AppHttpException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# === Router
app.include_router(routes_router)
