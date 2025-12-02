import logging
import secrets
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.environments import (
    APP_NAME,
    LOGGER_LEVEL,
    LOGGER_MIDDLEWARE_SHOW_HEADERS,
)

# Configuración del logger una sola vez
logger = logging.getLogger(APP_NAME)
logger.setLevel(LOGGER_LEVEL)
logger.propagate = False  # Evita que se duplique en el logger raiz

if not logger.hasHandlers():
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


class LoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        unique_id = secrets.token_hex(8)
        request.session["request_id"] = unique_id
        start_time = time.time()

        # Obtener datos de la solicitud
        method = request.method
        path = request.url.path
        query_string = request.url.query or None
        headers = dict(request.headers)
        client_ip = request.client.host if request.client else "unknown"

        try:
            body = await request.json()
        except Exception:
            body = "<no body>"

        logger_info_request = [
            str(unique_id),
            f"Host: {client_ip}",
            f"Request: {method} {path}",
            f"Body: {'<cannot show>' if path in ['/user/login'] else body}",
            f"Query: {query_string if query_string else '<no parameters>'}",
        ]
        if LOGGER_MIDDLEWARE_SHOW_HEADERS:
            logger_info_request.append(f"Headers: {headers}")

        logger.info(" | ".join(logger_info_request))

        # Procesar la solicitud
        response = await call_next(request)
        process_time = round(time.time() - start_time, 3)

        # Registrar respuesta
        logger_info_response = [
            str(unique_id),
            f"Host: {client_ip}",
            f"Response: {method} {path}",
            f"Status: {response.status_code}",
            f"Duration: {process_time}s",
        ]
        logger.info(" | ".join(logger_info_response))

        return response
