"""
Traducción de filtros y orden de listados a SQL parametrizado.

Contrato público: docs/development/api-contract.md. La validación de lo que envía el cliente
vive en app/utils/list_query.py; aquí solo se arma el SQL y lo usan los models.

Los nombres de columna NUNCA salen del cliente: vienen de constantes del model (whitelist
nombre público → columna), por eso interpolarlos es seguro. Los valores van siempre como
parámetros enlazados.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

# Carácter de escape para LIKE. No se usa "\" porque su significado depende de
# sql_mode (NO_BACKSLASH_ESCAPES); con "!" el escape es el mismo en cualquier configuración.
LIKE_ESCAPE_CHAR = "!"


@dataclass(frozen=True)
class SortTerm:
    """Un campo de ordenamiento ya validado: nombre público y dirección."""

    field: str
    descending: bool


def escape_like(text: str) -> str:
    """Escapa los comodines de LIKE para buscar el texto literal que envió el cliente."""
    escaped = text.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
    escaped = escaped.replace("%", f"{LIKE_ESCAPE_CHAR}%")
    return escaped.replace("_", f"{LIKE_ESCAPE_CHAR}_")


def order_by(terms: Sequence[SortTerm], columns: Mapping[str, str], *, tiebreaker: str) -> str:
    """
    Arma el ORDER BY desde términos validados y la whitelist del model.

    Siempre agrega `tiebreaker` (columna única, normalmente `id`) al final: sin un desempate,
    filas con el mismo valor pueden cambiar de orden entre consultas y repetirse o perderse
    entre páginas.
    """
    parts: list[str] = []
    for term in terms:
        column = columns.get(term.field)
        if column is None:
            # El schema permite un campo que el model no mapea: error de programación
            raise ValueError(f"Campo de orden sin columna en el model: {term.field}")
        direction = "DESC" if term.descending else "ASC"
        parts.append(f"{column} {direction}")

    ordered_columns = {part.split(" ")[0] for part in parts}
    if tiebreaker not in ordered_columns:
        parts.append(f"{tiebreaker} DESC")
    return "ORDER BY " + ", ".join(parts)


@dataclass
class WhereBuilder:
    """
    Acumula condiciones AND con sus parámetros. Un filtro con valor None (o lista vacía) no filtra.

    Uso en un model:
        builder = WhereBuilder()
        builder.equals("is_active", filters.is_active, param="is_active")
        builder.date_range("created_at", filters.created_at_from, filters.created_at_to,
                           param="created_at")
        where_sql, params = builder.build()
    """

    conditions: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    def equals(self, column: str, value: Any, *, param: str) -> None:
        if value is None:
            return
        self.conditions.append(f"{column} = :{param}")
        self.params[param] = value

    def any_of(self, column: str, values: Sequence[Any] | None, *, param: str) -> None:
        """`column IN (...)` con un parámetro por valor."""
        if not values:
            return
        placeholders: list[str] = []
        for index, value in enumerate(values):
            param_name = f"{param}_{index}"
            placeholders.append(f":{param_name}")
            self.params[param_name] = value
        self.conditions.append(f"{column} IN ({', '.join(placeholders)})")

    def number_range(self, column: str, minimum: Any, maximum: Any, *, param: str) -> None:
        """Rango numérico con ambos extremos inclusivos (`_min` / `_max`)."""
        if minimum is not None:
            self.conditions.append(f"{column} >= :{param}_min")
            self.params[f"{param}_min"] = minimum
        if maximum is not None:
            self.conditions.append(f"{column} <= :{param}_max")
            self.params[f"{param}_max"] = maximum

    def date_range(
        self,
        column: str,
        start: date | datetime | None,
        end: date | datetime | None,
        *,
        param: str,
    ) -> None:
        """
        Rango de fechas con ambos extremos inclusivos (`_from` / `_to`).

        Con solo fecha, `end` incluye el día completo: se traduce a `< día siguiente 00:00`
        (intervalo semiabierto) en vez de `<= 23:59:59`, que perdería fracciones de segundo y
        funciona igual con columnas DATE y DATETIME.
        """
        if start is not None:
            start_value = (
                start if isinstance(start, datetime) else datetime.combine(start, time.min)
            )
            self.conditions.append(f"{column} >= :{param}_from")
            self.params[f"{param}_from"] = start_value
        if end is not None:
            if isinstance(end, datetime):
                self.conditions.append(f"{column} <= :{param}_to")
                self.params[f"{param}_to"] = end
            else:
                next_day_start = datetime.combine(end + timedelta(days=1), time.min)
                self.conditions.append(f"{column} < :{param}_to")
                self.params[f"{param}_to"] = next_day_start

    def contains_text(self, columns: Sequence[str], text: str | None, *, param: str) -> None:
        """Búsqueda libre: el texto aparece en alguna de las columnas (LIKE '%texto%')."""
        if not text:
            return
        comparisons = [f"{column} LIKE :{param} ESCAPE '{LIKE_ESCAPE_CHAR}'" for column in columns]
        self.conditions.append("(" + " OR ".join(comparisons) + ")")
        self.params[param] = f"%{escape_like(text)}%"

    def build(self) -> tuple[str, dict[str, Any]]:
        """Retorna el `WHERE ...` (o "" sin condiciones) y sus parámetros."""
        if not self.conditions:
            return "", dict(self.params)
        return "WHERE " + " AND ".join(self.conditions), dict(self.params)
