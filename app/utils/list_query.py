"""
Query params estándar de los listados (contrato: docs/development/api-contract.md).

Cada endpoint de listado declara UN modelo que hereda de ListQuery y lo recibe con
`Annotated[XxxListQuery, Query()]`:

- page/size/sort se llaman y validan igual en toda la API.
- Un parámetro desconocido (?is_activ=true) responde 422 en vez de ignorarse (extra="forbid").
  Por eso la paginación vive dentro del modelo: FastAPI valida TODOS los query params contra
  él, y una dependencia aparte con page/size sería rechazada como parámetro desconocido.
- Los pares <campo>_from/<campo>_to y <campo>_min/<campo>_max se validan solos (inicio <= fin).

La traducción a SQL (WHERE, ORDER BY) está en app/core/sql_filters.py y la hacen los models.

Uso:
    class PostListQuery(ListQuery):
        sortable_fields = ("created_at", "title")
        default_sort = "-created_at"

        status: list[PostStatus] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
        created_at_from: DateFilter | None = None
        created_at_to: DateFilter | None = None
        q: SearchText | None = None

    @router.get("", response_model=ApiResponse[list[PostOut]])
    async def list_posts(query: Annotated[PostListQuery, Query()], posts: PostControllerDep):
        items, total = await posts.list_posts(query)
        return paginated(items, total=total, pagination=query)
"""

import re
from datetime import date, datetime, time
from typing import Annotated, Any, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainValidator,
    StringConstraints,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.core.environment import settings
from app.core.sql_filters import SortTerm

# Leído al importar (configurar por entorno): el límite forma parte del esquema OpenAPI (le=)
PAGINATION_MAX_SIZE = settings.PAGINATION_MAX_SIZE

# Tamaño de página cuando el cliente no envía ?size=
DEFAULT_PAGE_SIZE = 20
# Tope de página: evita OFFSET gigantes (?page=10**20) que revientan en SQL
MAX_PAGE = 1_000_000
# Campos máximos en ?sort=: más niveles no aportan y complican los índices
MAX_SORT_FIELDS = 3
# Valores máximos en un filtro repetido (?status=a&status=b): acota el tamaño del IN (...)
MAX_FILTER_VALUES = 50
# Búsqueda libre (?q=): con menos de 2 caracteres un LIKE '%x%' recorre toda la tabla
SEARCH_MIN_LENGTH = 2
SEARCH_MAX_LENGTH = 100

# Sufijos de los rangos que se validan solos: (inicio, fin)
_RANGE_SUFFIXES = (("_from", "_to"), ("_min", "_max"))

_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(?P<zone>Z|[+-]\d{2}:\d{2})?"
)
_DATE_FILTER_FORMAT = "debe ser una fecha (YYYY-MM-DD) o fecha y hora (YYYY-MM-DDTHH:MM:SS)"


def _parse_date_filter(value: Any) -> date | datetime:
    """
    'YYYY-MM-DD' → date (en un `_to` significa el día completo); con hora → datetime.

    Se parsea a mano porque Pydantic convierte '2026-10-09T00:00:00' en date, y un `_to`
    con hora exacta de medianoche terminaría incluyendo el día entero.
    Sin zona horaria: las fechas se comparan tal como están guardadas en la BD.
    """
    if isinstance(value, date):  # incluye datetime (subclase de date)
        return value
    if not isinstance(value, str):
        raise PydanticCustomError("date_filter_format", _DATE_FILTER_FORMAT)

    text = value.strip()
    if _DATE_ONLY.fullmatch(text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise PydanticCustomError("date_filter_format", _DATE_FILTER_FORMAT) from None

    match = _DATE_TIME.fullmatch(text)
    if match is None:
        raise PydanticCustomError("date_filter_format", _DATE_FILTER_FORMAT)
    if match.group("zone") is not None:
        raise PydanticCustomError(
            "date_filter_timezone", "debe enviarse sin zona horaria (YYYY-MM-DDTHH:MM:SS)"
        )
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise PydanticCustomError("date_filter_format", _DATE_FILTER_FORMAT) from None


# Filtro de fecha para <campo>_from / <campo>_to (ver _parse_date_filter)
DateFilter = Annotated[
    date | datetime,
    PlainValidator(_parse_date_filter),
    WithJsonSchema(
        {
            "type": "string",
            "description": "Fecha (YYYY-MM-DD) o fecha y hora sin zona (YYYY-MM-DDTHH:MM:SS)",
            "examples": ["2026-10-09", "2026-10-09T08:30:00"],
        }
    ),
]

# Búsqueda libre (?q=): sin espacios a los extremos, entre 2 y 100 caracteres
SearchText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=SEARCH_MIN_LENGTH, max_length=SEARCH_MAX_LENGTH
    ),
]


def _comparable(value: Any, *, is_range_end: bool) -> Any:
    """Normaliza date/datetime para comparar inicio y fin (un date de fin cubre el día completo)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.max if is_range_end else time.min)
    return value


class ListQuery(BaseModel):
    """Base de los query params de un listado: paginación, orden y rechazo de parámetros extra."""

    model_config = ConfigDict(extra="forbid")

    # Nombres públicos que el cliente puede usar en ?sort=. Vacío = no se ordena a pedido.
    sortable_fields: ClassVar[tuple[str, ...]] = ()
    # Orden sin ?sort= (mismo formato, ej. "-created_at"). None = solo el desempate por id.
    default_sort: ClassVar[str | None] = None

    page: int = Field(default=1, ge=1, le=MAX_PAGE, description="Número de página (inicia en 1)")
    size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=PAGINATION_MAX_SIZE,
        description=f"Elementos por página (máximo {PAGINATION_MAX_SIZE})",
    )
    sort: str | None = Field(default=None, description="Este listado no admite ordenamiento")

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls._check_range_field_order()
        if cls.sortable_fields:
            # La descripción de ?sort= en OpenAPI sale de la misma whitelist que se valida
            default_text = f" Por defecto: {cls.default_sort}." if cls.default_sort else ""
            cls.model_fields["sort"].description = (
                "Campos separados por coma; prefijo '-' = descendente (ej. -created_at). "
                f"Permitidos: {', '.join(cls.sortable_fields)}.{default_text}"
            )
            cls.model_rebuild(force=True)

    @classmethod
    def _check_range_field_order(cls) -> None:
        # El validador de rangos compara contra el inicio ya validado: debe declararse antes del fin
        field_names = list(cls.model_fields)
        for start_suffix, end_suffix in _RANGE_SUFFIXES:
            for position, name in enumerate(field_names):
                if not name.endswith(end_suffix):
                    continue
                start_name = name.removesuffix(end_suffix) + start_suffix
                if start_name in field_names and field_names.index(start_name) > position:
                    raise TypeError(f"{cls.__name__}: declarar {start_name} antes de {name}")

    @property
    def offset(self) -> int:
        # Listo para SQL: LIMIT size OFFSET offset
        return (self.page - 1) * self.size

    @property
    def sort_terms(self) -> list[SortTerm]:
        """Orden pedido (o el default del endpoint) ya validado contra la whitelist."""
        raw_sort = self.sort or self.default_sort
        if not raw_sort:
            return []
        return [
            SortTerm(field=term.removeprefix("-"), descending=term.startswith("-"))
            for term in raw_sort.split(",")
        ]

    @field_validator("sort")
    @classmethod
    def _validate_sort(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not cls.sortable_fields:
            raise PydanticCustomError("invalid_sort", "no está disponible en este listado")

        terms = [term.strip() for term in value.split(",")]
        if any(term in ("", "-") for term in terms):
            raise PydanticCustomError(
                "invalid_sort", "tiene un campo vacío (formato: campo o -campo, separados por coma)"
            )
        if len(terms) > MAX_SORT_FIELDS:
            raise PydanticCustomError(
                "invalid_sort",
                "admite como máximo {max_fields} campos",
                {"max_fields": MAX_SORT_FIELDS},
            )

        names = [term.removeprefix("-") for term in terms]
        unknown = [name for name in names if name not in cls.sortable_fields]
        if unknown:
            raise PydanticCustomError(
                "invalid_sort",
                "no admite {unknown}; campos permitidos: {allowed}",
                {"unknown": ", ".join(unknown), "allowed": ", ".join(cls.sortable_fields)},
            )
        if len(set(names)) != len(names):
            raise PydanticCustomError("invalid_sort", "repite un campo")
        return ",".join(terms)

    @field_validator("*")
    @classmethod
    def _validate_range_end(cls, value: Any, info: ValidationInfo) -> Any:
        """<campo>_to >= <campo>_from y <campo>_max >= <campo>_min (si ambos llegaron)."""
        field_name = info.field_name
        if value is None or field_name is None:
            return value
        for start_suffix, end_suffix in _RANGE_SUFFIXES:
            if not field_name.endswith(end_suffix):
                continue
            start_name = field_name.removesuffix(end_suffix) + start_suffix
            start_value = info.data.get(start_name)
            if start_value is None:
                continue
            start = _comparable(start_value, is_range_end=False)
            end = _comparable(value, is_range_end=True)
            if start > end:
                raise PydanticCustomError(
                    "invalid_range",
                    "debe ser mayor o igual a {start_name}",
                    {"start_name": start_name},
                )
        return value
