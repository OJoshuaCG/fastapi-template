"""
Conversión de errores de validación de Pydantic/FastAPI a mensajes en español.

FastAPI responde por defecto un 422 en inglés que incluye `input` (el valor enviado,
que puede traer datos personales). Aquí se convierte a `errors: [{field, message, type}]`
sin el valor enviado.
"""

from collections.abc import Iterable, Sequence
from typing import Any

# Prefijos de `loc` que no le dicen nada al cliente
_ROOTS = ("body", "query", "path", "header", "cookie")


def error_message(err: dict[str, Any]) -> str:
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    match kind:
        case "missing":
            return "es obligatorio"
        case "extra_forbidden":
            return "no se admite en esta solicitud"
        case "less_than_equal":
            return f"debe ser menor o igual a {ctx.get('le')}"
        case "greater_than_equal":
            return f"debe ser mayor o igual a {ctx.get('ge')}"
        case "less_than":
            return f"debe ser menor que {ctx.get('lt')}"
        case "greater_than":
            return f"debe ser mayor que {ctx.get('gt')}"
        case "string_too_short":
            return f"debe tener al menos {ctx.get('min_length')} caracteres"
        case "string_too_long":
            return f"debe tener como máximo {ctx.get('max_length')} caracteres"
        case "too_short":
            return f"debe tener al menos {ctx.get('min_length')} elementos"
        case "too_long":
            return f"debe tener como máximo {ctx.get('max_length')} elementos"
        case "string_pattern_mismatch":
            return "no tiene el formato esperado"
        case "literal_error" | "enum":
            return f"debe ser uno de: {ctx.get('expected')}"
        case "json_invalid":
            return "no es un JSON válido"
        case "int_parsing" | "int_type" | "int_from_float":
            return "debe ser un número entero"
        case "float_parsing" | "float_type" | "decimal_parsing" | "decimal_type":
            return "debe ser un número"
        case "bool_parsing" | "bool_type":
            return "debe ser verdadero o falso"
        case "string_type":
            return "debe ser texto"
        case "dict_type" | "model_type" | "model_attributes_type":
            return "debe ser un objeto"
        case "list_type":
            return "debe ser una lista"
        case "date_parsing" | "date_type" | "date_from_datetime_parsing":
            return "debe ser una fecha válida (YYYY-MM-DD)"
        case "datetime_parsing" | "datetime_type" | "datetime_from_date_parsing":
            return "debe ser una fecha y hora válida (ISO 8601)"
        case "uuid_parsing" | "uuid_type":
            return "debe ser un UUID válido"
        case "value_error":
            msg = str(err.get("msg", ""))
            if "email address" in msg:
                return "no es un correo electrónico válido"
            return msg.removeprefix("Value error, ")
        case "assertion_error":
            return str(err.get("msg", "")).removeprefix("Assertion failed, ")
    return str(err.get("msg", ""))


def field_name(loc: Iterable[Any]) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in _ROOTS:
        parts = parts[1:]
    return ".".join(parts) or "solicitud"


def format_validation_errors(raw_errors: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "field": field_name(err.get("loc", ())),
            "message": error_message(err),
            "type": err.get("type"),
        }
        for err in raw_errors
    ]
