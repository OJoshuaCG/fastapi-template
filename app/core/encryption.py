"""
Cifrado simétrico reversible (Fernet: AES-128-CBC + HMAC-SHA256, con timestamp).

Uso:
    from app.core.encryption import encrypt, decrypt, DecryptionError

    token = encrypt("dato sensible")      # str ASCII, guardar en VARCHAR/TEXT
    valor = decrypt(token)                # DecryptionError si fue alterado o la llave no coincide

Llaves: ENCRYPTION_KEYS (Fernet, separadas por coma). La PRIMERA cifra, TODAS descifran:
    rotar = agregar la nueva al inicio, re-cifrar con rotate(token) y después quitar la vieja.
Nunca usar SECRET_KEY como llave: un secreto por propósito.

Migrar datos de omnicanal (su llave es base64url(sha256(SECRET_KEY))):
    1. Obtener su llave: fernet_key_from_secret("<SECRET_KEY de omnicanal>")
    2. Ponerla AL FINAL de ENCRYPTION_KEYS (solo descifra), re-cifrar con rotate(token)
       y quitarla cuando no queden tokens viejos.

Sin ENCRYPTION_KEYS (solo development/test) se usa una llave temporal por proceso: lo cifrado
no se puede leer tras reiniciar. En staging/producción la variable es obligatoria (environment.py).
"""

import base64
import hashlib
from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.environment import parse_encryption_keys, settings


class DecryptionError(Exception):
    """El token no se pudo descifrar (alterado, corrupto o cifrado con otra llave)."""


@cache
def _fernet(raw_keys: str) -> MultiFernet:
    keys = parse_encryption_keys(raw_keys) or [Fernet.generate_key()]
    return MultiFernet([Fernet(key) for key in keys])


def _cipher() -> MultiFernet:
    # Cache por valor de la variable: los tests pueden cambiar settings.ENCRYPTION_KEYS
    return _fernet(settings.ENCRYPTION_KEYS.get_secret_value())


def _raw(token: str | bytes) -> bytes:
    return token.encode() if isinstance(token, str) else token


def encrypt(value: str | bytes) -> str:
    return _cipher().encrypt(_raw(value)).decode("ascii")


def decrypt_bytes(token: str | bytes, *, ttl: int | None = None) -> bytes:
    """Descifra; `ttl` (segundos) rechaza tokens más viejos (útil para enlaces temporales)."""
    try:
        return _cipher().decrypt(_raw(token), ttl=ttl)
    except (InvalidToken, ValueError, TypeError):
        # Sin el token en el mensaje: no filtrar datos cifrados a los logs
        raise DecryptionError("No se pudo descifrar el valor") from None


def decrypt(token: str | bytes, *, ttl: int | None = None) -> str:
    return decrypt_bytes(token, ttl=ttl).decode()


def rotate(token: str | bytes) -> str:
    """Re-cifra el token con la llave principal (primera de ENCRYPTION_KEYS)."""
    try:
        return _cipher().rotate(_raw(token)).decode("ascii")
    except (InvalidToken, ValueError, TypeError):
        raise DecryptionError("No se pudo descifrar el valor") from None


def fernet_key_from_secret(secret: str) -> str:
    """Llave Fernet derivada como en omnicanal (solo para migrar sus datos, no para uso nuevo)."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode("ascii")
