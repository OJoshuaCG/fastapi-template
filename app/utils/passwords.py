"""

Uso:
    from app.utils.passwords import encrypt_password, verify_password

    stored = encrypt_password(payload.password)          # guardar en users.encrypted_password
    stored = user["encrypted_password"] if user else None
    if not verify_password(credentials.password, stored):
        raise AppHttpException("Credenciales inválidas", 401)

    reveal_password(stored)   # SOLO auditoría/soporte: nunca en una respuesta ni en un log

Riesgo asumido: quien obtenga la BD Y ENCRYPTION_KEYS obtiene todas las contraseñas en claro.
Por eso la llave vive fuera de la BD (variable de entorno/gestor de secretos) y se respalda aparte.
Si un proyecto no necesita descifrarlas, usar un hash lento (argon2id) en su lugar.
"""

import hmac

from app.core.encryption import DecryptionError, decrypt, encrypt

# Se compara contra este valor cuando el usuario no existe: no revela si existe
_DUMMY = b"x" * 32


def encrypt_password(password: str) -> str:
    return encrypt(password)


def verify_password(password: str, stored: str | None) -> bool:
    """True si coincide. Usuario inexistente (None) o valor corrupto → False, sin excepción."""
    if stored is None:
        hmac.compare_digest(password.encode(), _DUMMY)
        return False
    try:
        plain = decrypt(stored)
    except DecryptionError:
        return False
    return hmac.compare_digest(password.encode(), plain.encode())


def reveal_password(stored: str) -> str:
    """Contraseña en claro (auditoría). Lanza DecryptionError si el valor no es válido."""
    return decrypt(stored)
