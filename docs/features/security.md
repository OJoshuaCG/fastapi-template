# Seguridad: cifrado, contraseñas e IDs públicos

| Necesidad | Herramienta | Secreto |
|---|---|---|
| Guardar un dato sensible y poder leerlo | `app/core/encryption.py` (`encrypt`/`decrypt`) | `ENCRYPTION_KEYS` |
| Contraseñas (auditables) | `app/utils/passwords.py` | `ENCRYPTION_KEYS` |
| No exponer IDs autoincrementales | `app/core/encoding.py` (`EncodedId`) | `ENCODING_ALPHABET` |
| Auth del proyecto (JWT, sesiones) | a implementar | `SECRET_KEY` |

**Un secreto por propósito.** Nunca derivar uno de otro ni usar `SECRET_KEY` para cifrar: si un secreto
se filtra o hay que rotarlo, no arrastra a los demás. En producción la app no arranca si
`SECRET_KEY`, `DB_PASS` y `ENCRYPTION_KEYS` se repiten.

---

## Cifrado reversible (`ENCRYPTION_KEYS`)

Fernet (AES-128-CBC + HMAC-SHA256, con timestamp) mediante `MultiFernet`.

```python
from app.core.encryption import DecryptionError, decrypt, encrypt, rotate

token = encrypt("CURP o dato sensible")    # str ASCII (~1.4× el tamaño + 100 chars)
valor = decrypt(token)                     # DecryptionError si fue alterado o la llave no coincide
valor = decrypt(token, ttl=3600)           # además rechaza tokens de más de 1 hora
```

Generar una llave:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- `ENCRYPTION_KEYS` = llaves separadas por coma. La **primera cifra**, **todas descifran**.
- Obligatoria en staging y producción. Una llave inválida impide arrancar en cualquier entorno.
- Sin la variable (solo development/test) se usa una llave temporal por proceso y se avisa al arrancar:
  lo cifrado no se podrá leer después de reiniciar.
- `DecryptionError` nunca incluye el token ni el valor (no filtra datos a logs).

### Rotar la llave

1. Generar una llave nueva y ponerla **al inicio**: `ENCRYPTION_KEYS=<nueva>,<vieja>`. Desplegar.
2. Re-cifrar lo guardado: `rotate(token)` (descifra con cualquiera, cifra con la nueva).
3. Cuando no queden tokens viejos, quitar la vieja: `ENCRYPTION_KEYS=<nueva>`.

### Migrar datos cifrados por omnicanal

omnicanal cifra con `Fernet(base64url(sha256(SECRET_KEY)))`. Para leer sus datos:

```python
from app.core.encryption import fernet_key_from_secret
print(fernet_key_from_secret("<SECRET_KEY de omnicanal>"))
```

Poner esa llave **al final** de `ENCRYPTION_KEYS` (solo descifra), re-cifrar con `rotate()` y quitarla al
terminar. No usar esa derivación para datos nuevos.

---

## Contraseñas: cifrado reversible

Decisión del equipo: las contraseñas se **cifran** (no se hashean) para poder descifrarlas al auditar
problemas de soporte.

```python
from app.utils.passwords import encrypt_password, reveal_password, verify_password

# Registro (en el controller, nunca en la route)
data["encrypted_password"] = encrypt_password(payload.password)

# Login
user = await users.find_for_login(username)          # incluye encrypted_password
stored = user["encrypted_password"] if user else None
if not verify_password(credentials.password, stored):
    raise AppHttpException("Credenciales inválidas", 401, code="invalid_credentials")

# Auditoría / soporte (explícito y buscable en el código)
reveal_password(stored)
```

- `verify_password` nunca lanza: usuario inexistente (`None`), valor corrupto o llave distinta → `False`.
  Compara en tiempo constante (`hmac.compare_digest`).
- Columna `VARCHAR(512)` (un token de 128 caracteres mide ~270). `max_length=128` en el schema.
- `reveal_password()` nunca en una respuesta de la API ni en un log.
- Las consultas que terminan en una respuesta nunca seleccionan `encrypted_password` (`_PUBLIC_COLUMNS`).

**Riesgo asumido**: quien obtenga la BD **y** `ENCRYPTION_KEYS` obtiene todas las contraseñas en claro.
Por eso:

- La llave vive fuera de la BD (variable de entorno o gestor de secretos), nunca en el repositorio.
- Se respalda **aparte** del backup de la BD (sin llave, el backup es ilegible; con la llave junto al
  backup, la protección desaparece).
- Acceso a la llave solo para quien opera producción.

Si un proyecto no necesita descifrar contraseñas, usar un hash lento (argon2id, p. ej. `pwdlib[argon2]`)
en lugar de este módulo.

---

## Encoding de IDs públicos (`app/core/encoding.py`, sqids)

La API expone `"Xk3pQ9aL"` en vez del autoincremental `15`: no se pueden enumerar recursos ni deducir
volúmenes (cuántos usuarios/pedidos hay).

```python
from app.core.encoding import EncodedId, EncodedIdOut, decode_id, encode_id

@router.get("/{user_id}")
async def get_user(user_id: EncodedId, users: UserControllerDep):   # entrada: string → int
    ...

class UserOut(BaseModel):
    id: EncodedIdOut                                                # salida: int → string

class TransferIn(BaseModel):
    target_account_id: EncodedId                                    # también en bodies
```

| Caso | Resultado |
|---|---|
| ID inválido en la URL (`/users/abc`, `/users/15`) | **404** (para el cliente, el recurso no existe) |
| ID inválido en query/body | 422 `ID inválido` |
| int crudo en el body (`{"target_account_id": 15}`) | 422 (si no, se podría enumerar) |
| Forma no canónica (otra cadena que decodifica al mismo número) | inválido |

- Dos tipos porque la entrada solo acepta el string y la salida recibe el int que devuelve el model.
- `ENCODING_ALPHABET` es propio de cada proyecto y **no debe cambiar** (invalidaría los IDs ya compartidos).
  En producción no puede ser el default. Generar uno barajado:

  ```bash
  uv run python -c "import random, string; a = list(string.ascii_letters + string.digits); random.shuffle(a); print(''.join(a))"
  ```

- `ENCODING_MIN_LENGTH` (8): longitud mínima.
- **Es ofuscación, no autorización**: cada endpoint debe validar que quien consulta tenga acceso al recurso.
- Internamente (models, controllers, SQL, logs) todo sigue siendo `int`.
