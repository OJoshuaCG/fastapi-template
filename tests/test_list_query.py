"""Query params de listados (ListQuery) y su traducción a SQL (sql_filters). No requieren BD."""

from datetime import date, datetime

import httpx2
import pytest
from pydantic import Field, ValidationError

from app.core.sql_filters import SortTerm, WhereBuilder, escape_like, order_by
from app.models.user_model import SORT_COLUMNS
from app.schemas.user import UserListQuery
from app.utils.list_query import MAX_SORT_FIELDS, DateFilter, ListQuery


class ItemListQuery(ListQuery):
    sortable_fields = ("created_at", "name", "price")
    default_sort = "-created_at"

    created_at_from: DateFilter | None = None
    created_at_to: DateFilter | None = None
    price_min: int | None = None
    price_max: int | None = None


def _error_types(exc: ValidationError) -> dict[str, str]:
    return {".".join(str(p) for p in err["loc"]): err["type"] for err in exc.errors()}


# ---------------------------------------------------------------------------
# Paginación y parámetros desconocidos
# ---------------------------------------------------------------------------


def test_offset_from_page_and_size() -> None:
    assert ItemListQuery(page=3, size=10).offset == 20


def test_unknown_parameter_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ItemListQuery.model_validate({"nmae": "typo"})
    assert _error_types(exc.value) == {"nmae": "extra_forbidden"}


async def test_unknown_query_param_is_422_with_standard_format(
    client: httpx2.AsyncClient,
) -> None:
    resp = await client.get("/api/v1/test/paginated", params={"page": 1, "pagee": 2})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["errors"] == [
        {"field": "pagee", "message": "no se admite en esta solicitud", "type": "extra_forbidden"}
    ]


# ---------------------------------------------------------------------------
# Ordenamiento
# ---------------------------------------------------------------------------


def test_sort_terms_parse_direction_and_order() -> None:
    query = ItemListQuery(sort="name,-price")
    assert query.sort_terms == [
        SortTerm(field="name", descending=False),
        SortTerm(field="price", descending=True),
    ]


def test_default_sort_applies_without_sort_param() -> None:
    assert ItemListQuery().sort_terms == [SortTerm(field="created_at", descending=True)]


@pytest.mark.parametrize(
    "raw_sort",
    [
        "password",  # fuera de la whitelist
        "name,,price",  # campo vacío
        "-",  # solo el prefijo
        "name,-name",  # campo repetido
        ",".join(["name", "price", "created_at", "name"][: MAX_SORT_FIELDS + 1]),  # demasiados
    ],
)
def test_invalid_sort_is_rejected(raw_sort: str) -> None:
    with pytest.raises(ValidationError) as exc:
        ItemListQuery(sort=raw_sort)
    assert _error_types(exc.value) == {"sort": "invalid_sort"}


def test_sort_on_list_without_sortable_fields_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ListQuery(sort="name")
    assert _error_types(exc.value) == {"sort": "invalid_sort"}


def test_sort_description_lists_allowed_fields() -> None:
    description = ItemListQuery.model_fields["sort"].description or ""
    assert "created_at, name, price" in description
    assert "-created_at" in description


def test_user_sortable_fields_have_sql_columns() -> None:
    # Un campo permitido en el schema sin columna en el model sería un 500 en runtime
    assert set(UserListQuery.sortable_fields) <= set(SORT_COLUMNS)


# ---------------------------------------------------------------------------
# Filtros de fecha y rangos
# ---------------------------------------------------------------------------


def test_date_only_and_datetime_are_distinguished() -> None:
    query = ItemListQuery.model_validate(
        {"created_at_from": "2026-10-09", "created_at_to": "2026-10-09T00:00:00"}
    )
    # La medianoche explícita NO se convierte en "día completo"
    assert query.created_at_from == date(2026, 10, 9)
    assert query.created_at_to == datetime(2026, 10, 9, 0, 0)


@pytest.mark.parametrize(
    ("raw", "error_type"),
    [
        ("09/10/2026", "date_filter_format"),
        ("20261009", "date_filter_format"),
        ("2026-02-30", "date_filter_format"),
        ("2026-10-09T08:00:00Z", "date_filter_timezone"),
        ("2026-10-09T08:00:00-06:00", "date_filter_timezone"),
    ],
)
def test_invalid_date_filter(raw: str, error_type: str) -> None:
    with pytest.raises(ValidationError) as exc:
        ItemListQuery.model_validate({"created_at_from": raw})
    assert _error_types(exc.value) == {"created_at_from": error_type}


def test_same_day_range_is_valid() -> None:
    query = ItemListQuery.model_validate(
        {"created_at_from": "2026-10-09", "created_at_to": "2026-10-09"}
    )
    assert query.created_at_from == query.created_at_to


@pytest.mark.parametrize(
    "params",
    [
        {"created_at_from": "2026-10-10", "created_at_to": "2026-10-09"},
        {"created_at_from": "2026-10-09T10:00:00", "created_at_to": "2026-10-09T09:00:00"},
        {"price_min": 500, "price_max": 100},
    ],
)
def test_range_start_after_end_is_rejected(params: dict) -> None:
    with pytest.raises(ValidationError) as exc:
        ItemListQuery.model_validate(params)
    end_field = next(name for name in params if name.endswith(("_to", "_max")))
    assert _error_types(exc.value) == {end_field: "invalid_range"}


def test_range_end_declared_before_start_fails_at_definition() -> None:
    with pytest.raises(TypeError, match="declarar price_min antes de price_max"):

        class WrongOrderQuery(ListQuery):
            price_max: int | None = Field(default=None)
            price_min: int | None = Field(default=None)


# ---------------------------------------------------------------------------
# Traducción a SQL
# ---------------------------------------------------------------------------


def test_order_by_appends_unique_tiebreaker() -> None:
    sql = order_by([SortTerm("name", descending=False)], {"name": "full_name"}, tiebreaker="id")
    assert sql == "ORDER BY full_name ASC, id DESC"
    assert order_by([], {}, tiebreaker="id") == "ORDER BY id DESC"


def test_order_by_rejects_field_without_column() -> None:
    with pytest.raises(ValueError, match="sin columna"):
        order_by([SortTerm("password", descending=False)], {"name": "name"}, tiebreaker="id")


def test_date_range_with_date_end_covers_whole_day() -> None:
    builder = WhereBuilder()
    builder.date_range("created_at", date(2026, 10, 1), date(2026, 10, 31), param="created")
    where, params = builder.build()
    assert where == "WHERE created_at >= :created_from AND created_at < :created_to"
    assert params == {
        "created_from": datetime(2026, 10, 1, 0, 0),
        "created_to": datetime(2026, 11, 1, 0, 0),  # día siguiente, exclusivo
    }


def test_date_range_with_datetime_end_is_inclusive() -> None:
    builder = WhereBuilder()
    builder.date_range("created_at", None, datetime(2026, 10, 9, 18, 0), param="created")
    assert builder.build() == (
        "WHERE created_at <= :created_to",
        {"created_to": datetime(2026, 10, 9, 18, 0)},
    )


def test_where_builder_ignores_empty_filters() -> None:
    builder = WhereBuilder()
    builder.equals("is_active", None, param="is_active")
    builder.any_of("status", [], param="status")
    builder.contains_text(["name"], None, param="q")
    assert builder.build() == ("", {})


def test_where_builder_combines_conditions_with_and() -> None:
    builder = WhereBuilder()
    builder.equals("is_active", True, param="is_active")
    builder.any_of("status", ["active", "pending"], param="status")
    builder.number_range("price", 100, None, param="price")
    where, params = builder.build()
    assert where == (
        "WHERE is_active = :is_active AND status IN (:status_0, :status_1) AND price >= :price_min"
    )
    assert params == {
        "is_active": True,
        "status_0": "active",
        "status_1": "pending",
        "price_min": 100,
    }


def test_text_search_escapes_like_wildcards() -> None:
    assert escape_like("50%_off!") == "50!%!_off!!"
    builder = WhereBuilder()
    builder.contains_text(["username", "email"], "a_b", param="q")
    where, params = builder.build()
    assert where == "WHERE (username LIKE :q ESCAPE '!' OR email LIKE :q ESCAPE '!')"
    assert params == {"q": "%a!_b%"}
