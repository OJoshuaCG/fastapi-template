# Paginación, filtros y orden de listados

Todo listado recibe sus query params con **un modelo que hereda de `ListQuery`** (`app/utils/list_query.py`), y el
model arma el SQL con `app/core/sql_filters.py`. Las reglas públicas están en el
[contrato de la API](../development/api-contract.md); aquí está cómo se implementan.

| Pieza | Dónde | Qué resuelve |
|---|---|---|
| `ListQuery` | `app/utils/list_query.py` | `page`, `size`, `sort`, `offset`; rechaza parámetros desconocidos (422); valida rangos `_from`/`_to` y `_min`/`_max` |
| `DateFilter` | `app/utils/list_query.py` | Fecha (`YYYY-MM-DD`, día completo) o fecha y hora sin zona |
| `SearchText` | `app/utils/list_query.py` | Texto de `?q=` (2–100 caracteres, sin espacios a los extremos) |
| `MAX_FILTER_VALUES` | `app/utils/list_query.py` | Tope de valores en un filtro repetido (`?status=a&status=b`) |
| `WhereBuilder` | `app/core/sql_filters.py` | `equals`, `any_of` (IN), `number_range`, `date_range`, `contains_text` (LIKE escapado) |
| `order_by` | `app/core/sql_filters.py` | `ORDER BY` desde la whitelist del model + desempate por `id` |
| `paginated()` | `app/utils/response.py` | Respuesta `{"data": [...], "pagination": {...}}` |

## Convención de nombres

- **Contrato público (query string, OpenAPI, respuesta):** siempre `page` y `size`. No existen los query params `limit`/`offset`.
- **Capa de datos (models y SQL):** `limit` y `offset` son argumentos internos que el controller pasa desde `query.size` y `query.offset`.
- **Variables de entorno:** solo `PAGINATION_MAX_SIZE`. El default (`20`), el tope de página (`1_000_000`), los campos
  máximos de `sort` (`3`) y los valores máximos de un filtro (`50`) son constantes en `app/utils/list_query.py`.

## Parámetros comunes

| Query param | Default | Validación |
|---|---|---|
| `page` | `1` | `>= 1` y `<= 1_000_000` (evita `OFFSET` gigantes) |
| `size` | `20` | `>= 1` y `<= PAGINATION_MAX_SIZE` |
| `sort` | `default_sort` del endpoint | Campos de `sortable_fields`, `-` = descendente, máx. 3 |

```env
# Máximo por página. Hard cap en código: 200 (un valor mayor se recorta a 200)
PAGINATION_MAX_SIZE=50
```

Un valor fuera de rango o un parámetro desconocido responde 422 con el formato estándar:

```json
{"detail": {"msg": "Error de validación: is_activ no se admite en esta solicitud", "type": "ValidationError",
            "code": "validation_error",
            "errors": [{"field": "is_activ", "message": "no se admite en esta solicitud", "type": "extra_forbidden"}]}}
```

## Uso (ejemplo `posts`)

**Schema** (`app/schemas/post.py`): declara los filtros del endpoint. Un `_from` va antes de su `_to` (si no, la clase
falla al importarse).

```python
from typing import Literal

from pydantic import Field

from app.utils.list_query import MAX_FILTER_VALUES, DateFilter, ListQuery, SearchText


class PostListQuery(ListQuery):
    sortable_fields = ("created_at", "title")   # la descripción de ?sort= en OpenAPI sale de aquí
    default_sort = "-created_at"

    status: list[Literal["draft", "published"]] | None = Field(default=None, max_length=MAX_FILTER_VALUES)
    created_at_from: DateFilter | None = Field(default=None, description="Creados desde (inclusive)")
    created_at_to: DateFilter | None = Field(default=None, description="Creados hasta (inclusive)")
    q: SearchText | None = Field(default=None, description="Texto contenido en el título")
```

**Model** (`app/models/post_model.py`): la whitelist de orden y el `WHERE` viven aquí; el mismo `WHERE` sirve para
el listado y el `count`, así `total` coincide con lo listado.

```python
from app.core.sql_filters import SortTerm, WhereBuilder, order_by

SORT_COLUMNS = {"created_at": "created_at", "title": "title"}   # nombre público → columna


@dataclass(frozen=True)
class PostFilters:
    status: Sequence[str] | None = None
    created_at_from: date | datetime | None = None
    created_at_to: date | datetime | None = None
    q: str | None = None


class PostModel:
    async def find_all(self, *, limit: int, offset: int, filters: PostFilters,
                       sort: Sequence[SortTerm] = ()) -> list[dict]:
        where, params = self._filters(filters)
        order = order_by(sort, SORT_COLUMNS, tiebreaker="id")
        return await self.db.fetch_all(
            f"SELECT id, title, status, created_at FROM posts {where} {order} LIMIT :limit OFFSET :offset",
            {**params, "limit": limit, "offset": offset},
        )

    async def count(self, *, filters: PostFilters) -> int:
        where, params = self._filters(filters)
        return int(await self.db.fetch_value(f"SELECT COUNT(*) FROM posts {where}", params) or 0)

    @staticmethod
    def _filters(filters: PostFilters) -> tuple[str, dict[str, Any]]:
        builder = WhereBuilder()
        builder.any_of("status", filters.status, param="status")
        builder.date_range("created_at", filters.created_at_from, filters.created_at_to, param="created_at")
        builder.contains_text(("title",), filters.q, param="q")
        return builder.build()
```

**Controller**: recibe el schema, arma los filtros del model y retorna `(items, total)`.

```python
async def list_posts(self, query: PostListQuery) -> tuple[list[dict], int]:
    filters = PostFilters(status=query.status, created_at_from=query.created_at_from,
                          created_at_to=query.created_at_to, q=query.q)
    # Secuencial: cada consulta toma y devuelve su conexión al pool
    items = await self.posts.find_all(limit=query.size, offset=query.offset, filters=filters,
                                      sort=query.sort_terms)
    total = await self.posts.count(filters=filters)
    return items, total
```

**Route**: un solo parámetro con todo el query.

```python
@router.get("", response_model=ApiResponse[list[PostOut]])
async def list_posts(query: Annotated[PostListQuery, Query()], posts: PostControllerDep):
    items, total = await posts.list_posts(query)
    return paginated(items, total=total, pagination=query)
```

Un listado sin filtros ni orden usa `Annotated[ListQuery, Query()]` directo (ver `GET /api/v1/test/paginated`).
El ejemplo real completo es `GET /api/v1/users`: `UserListQuery` (`app/schemas/user.py`), `UserModel._filters()` y
`SORT_COLUMNS` (`app/models/user_model.py`).

No combinar `ListQuery` con otros parámetros de query sueltos en la route: con `extra="forbid"` el modelo valida
**todos** los query params y rechazaría los que no declara. Todo filtro va dentro del modelo.
`tests/test_architecture.py` lo verifica: un `GET` que responde `ApiResponse[list[...]]` debe recibir exactamente un
modelo que herede de `ListQuery` y ningún otro query param (tampoco por `Depends`).

## Respuesta

```http
GET /api/v1/users?page=2&size=10&sort=username
```

```json
{
  "data": [{"id": "Xk3pQ9aL", "username": "..."}],
  "pagination": {
    "page": 2,
    "size": 10,
    "total": 35,
    "pages": 4,
    "has_next": true,
    "has_prev": true
  }
}
```

- `pages = ceil(total / size)`, o `0` si `total == 0`.
- `has_next = page < pages`, `has_prev = page > 1`.
- Una página fuera de rango (`page > pages`) responde 200 con `data: []`.

## Cuándo usar cursor (excepción, no implementado)

`page`/`size` es el estándar de toda la API: un solo contrato para los clientes, con salto a cualquier página y `total`.
La paginación por cursor (keyset: `WHERE id < :ultimo_id ORDER BY id DESC LIMIT :n`) **no se puede expresar con
`page`/`size`**: no hay "página N" ni `total`, a cambio de ser estable ante inserciones y de costo constante en tablas grandes.

Se justifica solo en un endpoint concreto (feed, tabla que solo crece y es muy grande). Si aparece:

- Modelo de query propio (`?cursor=&size=`) y respuesta propia, sin heredar de `ListQuery`.
- Cursor opaco para el cliente (no exponer el id crudo) y orden total determinista (columna única como desempate).
- Documentarlo en ese endpoint como excepción al estándar.

Mientras tanto, el costo de `OFFSET` está acotado por `page ≤ 1_000_000` y `PAGINATION_MAX_SIZE`; no desaparece.

---

Ver también: [Contrato de la API](../development/api-contract.md) · [Formato de Respuestas](response-format.md) · [Base de Datos](database.md)
