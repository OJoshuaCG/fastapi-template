# Seguridad: cifrado, contraseñas y encoding de IDs

Reglas de cifrado, contraseñas e IDs públicos. Detalle ampliado en `docs/features/security.md`.

## Seguridad: cifrado, contraseñas y encoding de IDs

```python
from app.core.encryption import encrypt, decrypt, rotate, DecryptionError   # datos sensibles reversibles
from app.utils.passwords import encrypt_password, verify_password, reveal_password
from app.core.encoding import EncodedId, EncodedIdOut, encode_id, decode_id
```

- **Cifrado** (`ENCRYPTION_KEYS`, MultiFernet): la primera llave cifra, todas descifran. Rotar = nueva llave
  al inicio → `rotate(token)` → quitar la vieja. `DecryptionError` nunca incluye el token. Sin la variable
  (solo dev/test) se usa una llave temporal y se avisa al arrancar. Datos de omnicanal: agregar
  `fernet_key_from_secret(<su SECRET_KEY>)` al final de `ENCRYPTION_KEYS` y re-cifrar con `rotate()`.
- **Contraseñas: cifrado reversible** (decisión del equipo, para auditar). El controller cifra
  (`encrypt_password`), el login compara con `verify_password(pw, stored_or_None)` (nunca lanza; `None` =
  usuario inexistente). `reveal_password()` solo para auditoría/soporte: nunca en respuestas ni logs.
  Riesgo: BD + `ENCRYPTION_KEYS` = todas las contraseñas → la llave vive fuera de la BD y se respalda aparte.
  Columna `VARCHAR(512)`; `max_length=128` en el schema.
- **Encoding de IDs** (`app/core/encoding.py`, sqids, `ENCODING_ALPHABET` propio y fijo por proyecto): `EncodedId` en la **entrada**
  (path/query/body: solo acepta el string; inválido en la URL → 404, en el body → 422) y `EncodedIdOut` en
  la **salida** (el int del model se serializa como string). Es ofuscación, no autorización: validar acceso igual.

Detalle: `docs/features/services.md` y `docs/features/security.md`.

