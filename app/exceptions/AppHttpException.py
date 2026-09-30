from typing import Any

from fastapi import HTTPException


class AppHttpException(HTTPException):
    """
    Excepción controlada de la aplicación. Todo error esperado debe lanzarse con esta clase.

    Campos públicos (llegan al cliente):
        message:  texto legible y seguro para el usuario final. Nunca meter str(e) aquí.
        code:     código estable en snake_case para que el frontend decida (ej. "user_conflict").
        reason:   sub-causa estable (ej. "pool_exhausted").
        errors:   lista [{field, message, type}] SIN el valor enviado por el usuario.
        public:   datos adicionales del contrato (ej. {"existing": {...}}).
        headers:  headers de la respuesta (ej. Retry-After, WWW-Authenticate).

    Campo privado (solo logs y respuesta en development):
        context:  variables útiles para depurar (ids, payloads a APIs externas...).
                  Nunca el body entrante completo (PII).

    Uso:
        raise AppHttpException("Usuario no encontrado", 404, {"user_id": user_id})
        raise AppHttpException("El email ya está en uso", 409, code="user_conflict")

    El archivo/línea de un error no controlado (500) sale del traceback en el log y, en
    development, en `loc` de la respuesta.
    """

    def __init__(
        self,
        message: str = "Error interno del servidor",
        status_code: int = 500,
        context: Any = None,
        *,
        code: str | None = None,
        reason: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        public: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.message = message
        self.context = context
        self.code = code
        self.reason = reason
        self.errors = errors
        self.public = public

    def __str__(self) -> str:
        return f"{self.status_code}: {self.message}"
