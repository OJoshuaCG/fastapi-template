# Paginación

`app/utils/pagination.py` define una dependencia reutilizable (`PaginationDep`) que lee `?page=&size=` y calcula el `offset`. La respuesta se arma con `paginated()` de `app/utils/response.py`.

## Parámetros

| Query param | Default | Validación |
|---|---|---|
| `page` | `1` | `>= 1` y `<= 1_000_000` (evita `OFFSET` gigantes) |
| `size` | `20` | `>= 1` y `<= PAGINATION_MAX_SIZE` |

```env
# Máximo por página. Hard cap en código: 200 (un valor mayor se recorta a 200)
PAGINATION_MAX_SIZE=50
```

`PaginationParams` expone `page`, `size` y `offset = (page - 1) * size`, listo para `LIMIT :limit OFFSET :offset`.

Un valor fuera de rango responde 422 con el formato estándar:

```json
{"detail": {"msg": "Error de validación: size debe ser menor o igual a 50", "type": "ValidationError", "code": "validation_error", "errors": [...]}}
```

## Uso

**Model**:

```python
async def find_all(self, *, limit: int, offset: int) -> list[dict]:
    return await self.db.fetch_all(
        "SELECT id, title FROM posts ORDER BY id DESC LIMIT :limit OFFSET :offset",
        {"limit": limit, "offset": offset},
    )

async def count(self) -> int:
    return int(await self.db.fetch_value("SELECT COUNT(*) FROM posts") or 0)
```

**Controller**: retorna `(items, total)`.

```python
from app.utils.pagination import PaginationParams


async def list_posts(self, pagination: PaginationParams) -> tuple[list[dict], int]:
    # Secuencial: cada consulta toma y devuelve su conexión al pool.
    items = await self.posts.find_all(limit=pagination.size, offset=pagination.offset)
    total = await self.posts.count()
    return items, total
```

**Route**:

```python
from app.utils.pagination import PaginationDep
from app.utils.response import ApiResponse, paginated


@router.get("", response_model=ApiResponse[list[PostOut]])
async def list_posts(pagination: PaginationDep, posts: PostControllerDep):
    items, total = await posts.list_posts(pagination)
    return paginated(items, total=total, pagination=pagination)
```

El ejemplo real es `GET /api/v1/users` (`app/routes/v1/users.py`), que además acepta el filtro `?is_active=`.

## Respuesta

```http
GET /api/v1/users?page=2&size=10
```

```json
{
  "data": [{"id": 11, "username": "..."}],
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

## Filtros

Los filtros van como query params adicionales y se aplican **igual** en `find_all` y en `count`, para que `total` sea coherente. `UserModel._filters()` es un ejemplo de cómo armar el `WHERE` una sola vez.

---

Ver también: [Formato de Respuestas](response-format.md) · [Base de Datos](database.md)
