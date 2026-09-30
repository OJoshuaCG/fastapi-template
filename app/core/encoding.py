"""
IDs públicos ofuscados (sqids): la API expone "Xk3pQ9aL" en vez del autoincremental 15.

Uso:
    from app.core.encoding import EncodedId, EncodedIdOut

    @router.get("/{user_id}")
    async def get_user(user_id: EncodedId):  # ENTRADA (path/query/body): string → int
        ...                                  # ID inválido en la URL → 404; en el body → 422

    class UserOut(BaseModel):
        id: EncodedIdOut                     # SALIDA: el int de la BD sale como string

Son dos tipos porque la entrada solo acepta el string (un int crudo en el body se rechaza:
si no, los IDs se podrían enumerar) y la salida recibe el int que devuelve el model.

    encode_id(15) / decode_id("Xk3pQ9aL")    # uso manual (decode_id → None si es inválido)

Es OFUSCACIÓN, no seguridad: evita enumerar IDs y exponer volúmenes, pero cada endpoint debe
seguir validando que quien consulta tenga acceso al recurso. ENCODING_ALPHABET es propio del
proyecto y no debe cambiar (invalidaría los IDs ya compartidos).
"""

from functools import cache
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema
from pydantic_core import PydanticCustomError
from sqids import Sqids

from app.core.environment import settings

# Tipo de error de pydantic: el handler de validación lo responde como 404 en path params
ENCODED_ID_ERROR = "encoded_id"


@cache
def _sqids(alphabet: str, min_length: int) -> Sqids:
    return Sqids(alphabet=alphabet, min_length=min_length)


def _codec() -> Sqids:
    return _sqids(settings.ENCODING_ALPHABET, settings.ENCODING_MIN_LENGTH)


def encode_id(value: int) -> str:
    if value < 0:
        raise ValueError("Solo se codifican IDs no negativos")
    return _codec().encode([value])


def decode_id(value: str) -> int | None:
    """int del ID público, o None si no es válido (incluye formas no canónicas)."""
    codec = _codec()
    numbers = codec.decode(value)
    # Varias cadenas pueden decodificar al mismo número: aceptar solo la canónica
    if len(numbers) != 1 or codec.encode(numbers) != value:
        return None
    return numbers[0]


def _validate(value: object) -> int:
    if isinstance(value, str):
        decoded = decode_id(value)
        if decoded is not None:
            return decoded
    raise PydanticCustomError(ENCODED_ID_ERROR, "ID inválido")


_SCHEMA = WithJsonSchema({"type": "string", "examples": ["Xk3pQ9aL"]})

# Entrada: solo el string público (path, query o body)
EncodedId = Annotated[
    int,
    BeforeValidator(_validate),
    PlainSerializer(encode_id, return_type=str),
    _SCHEMA,
]

# Salida: el int interno se serializa como string público
EncodedIdOut = Annotated[int, PlainSerializer(encode_id, return_type=str), _SCHEMA]
