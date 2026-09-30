"""IDs públicos (app/core/encoding.py)."""

import pytest
from pydantic import BaseModel, ValidationError

from app.core.encoding import EncodedId, EncodedIdOut, decode_id, encode_id
from app.core.environment import settings


class RefIn(BaseModel):
    user_id: EncodedId


class RefOut(BaseModel):
    id: EncodedIdOut


@pytest.mark.parametrize("value", [0, 1, 15, 2**31 - 1, 2**53])
def test_round_trip(value: int) -> None:
    public = encode_id(value)
    assert len(public) >= settings.ENCODING_MIN_LENGTH
    assert decode_id(public) == value


@pytest.mark.parametrize("raw", ["", "15", "abc", "!!!!!!!!", "ñandúñandú"])
def test_invalid_is_none(raw: str) -> None:
    assert decode_id(raw) is None


def test_non_canonical_form_is_rejected() -> None:
    public = encode_id(15)
    assert decode_id(public + public[-1]) != 15


def test_alphabet_changes_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    before = encode_id(15)
    monkeypatch.setattr(settings, "ENCODING_ALPHABET", "k3G7QAe51FCsPW92uEOyq4Bg6Sp8YzVTmnU0li")
    assert encode_id(15) != before


def test_input_accepts_only_public_string() -> None:
    assert RefIn(user_id=encode_id(7)).user_id == 7
    with pytest.raises(ValidationError, match="ID inválido"):
        RefIn.model_validate({"user_id": 7})  # un int crudo permitiría enumerar
    with pytest.raises(ValidationError, match="ID inválido"):
        RefIn.model_validate({"user_id": "no-valido"})


def test_output_serializes_int_as_public_string() -> None:
    assert RefOut(id=7).model_dump(mode="json") == {"id": encode_id(7)}
    assert RefOut.model_json_schema()["properties"]["id"]["type"] == "string"


def test_negative_ids_are_not_encoded() -> None:
    with pytest.raises(ValueError):
        encode_id(-1)
