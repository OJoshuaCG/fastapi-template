"""Cifrado reversible (app/core/encryption.py) y contraseñas (app/utils/passwords.py)."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core import encryption
from app.core.encryption import DecryptionError, decrypt, encrypt, fernet_key_from_secret, rotate
from app.core.environment import settings
from app.utils.passwords import encrypt_password, reveal_password, verify_password

KEY = settings.ENCRYPTION_KEYS.get_secret_value()  # llave fija de conftest
# Token generado una vez con KEY: si cambia la llave o el formato, este test lo detecta
FIXED_TOKEN = Fernet(KEY.encode()).encrypt(b"hola")


def use_keys(monkeypatch: pytest.MonkeyPatch, *keys: str) -> None:
    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", SecretStr(",".join(keys)))


def test_round_trip_and_randomized() -> None:
    token = encrypt("dato sensible ñ")
    assert decrypt(token) == "dato sensible ñ"
    assert encrypt("x") != encrypt("x")  # IV aleatorio: mismo texto, distinto token


def test_decrypts_token_from_fixed_key() -> None:
    assert decrypt(FIXED_TOKEN) == "hola"


@pytest.mark.parametrize("token", ["", "basura", encrypt("x")[:-4] + "AAAA"])
def test_tampered_or_garbage_raises_without_content(token: str) -> None:
    with pytest.raises(DecryptionError) as exc:
        decrypt(token)
    assert str(exc.value) == "No se pudo descifrar el valor"  # nunca el token


def test_foreign_key_cannot_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    token = encrypt("x")
    use_keys(monkeypatch, Fernet.generate_key().decode())
    with pytest.raises(DecryptionError):
        decrypt(token)


def test_rotation_with_multiple_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    old_token = encrypt("secreto")
    new_key = Fernet.generate_key().decode()
    use_keys(monkeypatch, new_key, KEY)  # nueva primero: cifra; la vieja solo descifra
    assert decrypt(old_token) == "secreto"
    rotated = rotate(old_token)

    use_keys(monkeypatch, new_key)  # quitar la vieja
    assert decrypt(rotated) == "secreto"
    with pytest.raises(DecryptionError):
        decrypt(old_token)


def test_without_keys_uses_ephemeral_key(monkeypatch: pytest.MonkeyPatch) -> None:
    use_keys(monkeypatch)
    assert decrypt(encrypt("x")) == "x"
    encryption._fernet.cache_clear()  # "reinicio": nueva llave temporal
    with pytest.raises(DecryptionError):
        decrypt(FIXED_TOKEN)


def test_omnicanal_key_derivation_is_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    # omnicanal: Fernet(base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY).digest()))
    legacy_key = fernet_key_from_secret("omnicanal-secret")
    legacy_token = Fernet(legacy_key.encode()).encrypt(b"dato viejo").decode()
    use_keys(monkeypatch, KEY, legacy_key)
    assert decrypt(legacy_token) == "dato viejo"
    assert decrypt(rotate(legacy_token)) == "dato viejo"


def test_ttl_rejects_old_tokens() -> None:
    old = Fernet(KEY.encode()).encrypt_at_time(b"x", current_time=0)
    with pytest.raises(DecryptionError):
        decrypt(old, ttl=60)


# ---- Contraseñas ---------------------------------------------------------------------- #


def test_password_verify_and_reveal() -> None:
    stored = encrypt_password("S3cret!ñ")
    assert "S3cret" not in stored
    assert verify_password("S3cret!ñ", stored) is True
    assert verify_password("s3cret!ñ", stored) is False
    assert reveal_password(stored) == "S3cret!ñ"


def test_password_fits_column() -> None:
    # users.encrypted_password es VARCHAR(512); UserCreate.password tiene max_length=128
    assert len(encrypt_password("ñ" * 128)) <= 512


@pytest.mark.parametrize("stored", [None, "", "basura", "scrypt$legacy"])
def test_password_verify_never_raises(stored: str | None) -> None:
    assert verify_password("x", stored) is False
