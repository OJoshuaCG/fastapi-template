from typing import Any

# Coincidencia por subcadena: "user_password", "api_key", "access_token" también se enmascaran
_SENSITIVE_PARTS = ("password", "passwd", "secret", "token", "authorization", "api_key", "apikey")
_SENSITIVE_EXACT = {"pass", "pwd", "key", "cookie"}
_MASK = "***"


def is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return k in _SENSITIVE_EXACT or any(part in k for part in _SENSITIVE_PARTS)


def sanitize(data: Any) -> Any:
    """
    Enmascara valores sensibles de forma recursiva (dicts, listas, tuplas) antes de loguear
    o devolver `context` en development. No modifica el objeto original.
    """
    if isinstance(data, dict):
        return {
            k: _MASK if isinstance(k, str) and is_sensitive_key(k) else sanitize(v)
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return type(data)(sanitize(v) for v in data)
    return data
