# Receta: crear una feature

Pasos completos para agregar una feature (tabla, model, controller, schemas, route, test), con el ejemplo de referencia `users`.

## Crear una feature (receta completa)

### 1. Tabla (`database/init/00N_posts.sql`)

Script nuevo con el siguiente número libre. Nunca modificar un script ya aplicado en otro entorno.

```sql
CREATE TABLE IF NOT EXISTS posts (
    id         INT          NOT NULL AUTO_INCREMENT,
    title      VARCHAR(200) NOT NULL,
    content    TEXT         NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

Aplicarlo con el gestor de BD, el cliente `mariadb` o por el DBA:

```bash
mariadb -h <host> -u <user> -p <db> < database/init/00N_posts.sql
```

Los tests borran todas las tablas y aplican `database/init/*.sql` + `database/procedures/*.sql` solos
(fixture `database_schema`, `sql_statements()` entiende `DELIMITER`). Stored procedures en
`database/procedures/`. Con docker-compose la BD arranca vacía: cada desarrollador aplica `database/init/*.sql`
y `database/procedures/*.sql` con su gestor de BD o el cliente `mariadb` (con `DB_USER`/`DB_PASS`);
ver `database/README.md`.

### 2. Model (`app/models/post_model.py`)

```python
from typing import Annotated, Any
from fastapi import Depends
from app.core.database import Database, DatabaseDep
from app.core.sql_filters import SortTerm, order_by

_UPDATABLE = frozenset({"title", "content"})   # whitelist si se arman columnas dinámicas
SORT_COLUMNS = {"created_at": "created_at", "title": "title"}   # whitelist de ?sort=

class PostModel:
    def __init__(self, db: Database):
        self.db = db

    async def find_by_id(self, post_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM posts WHERE id = :id", {"id": post_id})

    async def find_all(self, *, limit: int, offset: int, sort: Sequence[SortTerm] = ()) -> list[dict]:
        order = order_by(sort, SORT_COLUMNS, tiebreaker="id")   # columnas de la whitelist, no del cliente
        return await self.db.fetch_all(
            f"SELECT * FROM posts {order} LIMIT :limit OFFSET :offset",
            {"limit": limit, "offset": offset},
        )

    async def count(self) -> int:
        return int(await self.db.fetch_value("SELECT COUNT(*) FROM posts") or 0)

    async def create(self, data: dict[str, Any]) -> int:
        result = await self.db.execute(
            "INSERT INTO posts (title, content) VALUES (:title, :content)", data
        )
        return int(result.lastrowid or 0)

def get_post_model(db: DatabaseDep) -> PostModel:
    return PostModel(db)

PostModelDep = Annotated[PostModel, Depends(get_post_model)]
```

### 3. Controller (`app/controllers/post_controller.py`)

Recibe los **schemas** de la route (no dicts armados por ella) y decide cómo persistirlos.

```python
class PostController:
    def __init__(self, posts: PostModel):
        self.posts = posts

    async def get_post(self, post_id: int) -> dict:
        post = await self.posts.find_by_id(post_id)
        if not post:
            raise AppHttpException("Post no encontrado", 404, {"post_id": post_id}, code="post_not_found")
        return post

    async def list_posts(self, query: PostListQuery) -> tuple[list[dict], int]:
        # Filtros y orden: ver docs/features/pagination.md (PostFilters, WhereBuilder, order_by)
        items = await self.posts.find_all(limit=query.size, offset=query.offset, sort=query.sort_terms)
        return items, await self.posts.count()

    async def create_post(self, payload: PostCreate) -> dict:
        post_id = await self.posts.create(payload.model_dump())
        return await self.get_post(post_id)

def get_post_controller(posts: PostModelDep) -> PostController:
    return PostController(posts)

PostControllerDep = Annotated[PostController, Depends(get_post_controller)]
```

No hacer "SELECT para ver si existe" antes de un INSERT: tiene carrera. El índice UNIQUE decide y
la capa de datos lanza 409 (`reason == "duplicate"`); el controller puede re-mapear el mensaje.

### 4. Schemas (`app/schemas/post.py`)

```python
class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str | None = None

class PostListQuery(ListQuery):            # query de GET /posts: page/size/sort + filtros
    sortable_fields = ("created_at", "title")
    default_sort = "-created_at"

class PostOut(BaseModel):
    id: EncodedIdOut          # el int de la BD sale como string público ("Xk3pQ9aL")
    title: str
    content: str | None
    created_at: datetime
```

### 5. Routes (`app/routes/v1/posts.py`) y registro en `app/routes/v1/routes.py`

```python
router = APIRouter(prefix="/posts", tags=["Posts"])

@router.get("", response_model=ApiResponse[list[PostOut]])
async def list_posts(query: Annotated[PostListQuery, Query()], posts: PostControllerDep):
    items, total = await posts.list_posts(query)   # page/size/sort/filtros; desconocidos → 422
    return paginated(items, total=total, pagination=query)

@router.get("/{post_id}", response_model=ApiResponse[PostOut])
async def get_post(post_id: EncodedId, posts: PostControllerDep):   # llega como int; inválido → 404
    return success(data=await posts.get_post(post_id))

@router.post("", response_model=ApiResponse[PostOut], status_code=status.HTTP_201_CREATED)
async def create_post(payload: PostCreate, posts: PostControllerDep):
    return success(data=await posts.create_post(payload), message="Post creado")
```

```python
# app/routes/v1/routes.py → build_v1_router()
router.include_router(posts.router)
```

### 6. Test (`tests/test_posts_api.py`)

```python
pytestmark = pytest.mark.db

async def test_get_post_404(client: httpx2.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/posts/{encode_id(999999)}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "post_not_found"
```

Ejemplo completo de referencia: `users` (`app/models/user_model.py`, `app/controllers/user_controller.py`,
`app/routes/v1/users.py`, `tests/test_users_api.py`).

