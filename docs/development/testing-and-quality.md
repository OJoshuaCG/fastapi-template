# Tests y calidad

Comandos de verificación y convenciones de pruebas. Los tests se corren solo cuando el usuario lo pide.

## Tests

```bash
docker compose -f docker-compose.test.yml up -d --wait   # MariaDB en RAM, puerto 3307
uv run pytest                                            # los tests @db se saltan si no hay BD
uv run ruff check . && uv run ruff format --check .
uv run pyright                                           # tipos (Ruff no verifica tipos); modo standard sobre app/ y main.py
uv run pytest --cov                                      # cobertura de app/ (con ramas); se mide, sin umbral mínimo
uv run pip-audit                                         # vulnerabilidades conocidas en dependencias
```

- Fixtures en `tests/conftest.py`: `client` (httpx2 + lifespan), `db`, `v1_app`, `clean_users`.
- Tests con BD: `pytestmark = pytest.mark.db`. Se prueba contra MariaDB real, no SQLite.
- Override de dependencias: `v1_app.dependency_overrides[get_user_controller] = Fake`.
- `ENV_FILE=""` en tests: el `.env` local no se lee.
- `filterwarnings`: `DeprecationWarning`, `FastAPIDeprecationWarning`, `StarletteDeprecationWarning` y
  `UvicornDeprecationWarning` (y `RuntimeWarning`) son errores.

## Calidad del código

- **Tipos:** pyright en modo `standard` sobre `app/` y `main.py`. Ruff no verifica tipos.
- **Cobertura:** se mide con `pytest-cov`; no hay umbral mínimo ni CI configurado.
- **Docstrings:** solo en API pública o no obvia (`core/`, `utils/`, dependencias reutilizables) y cuando hay un
  contrato que la firma no muestra (errores, unidades, efectos). No repetir lo que dicen el nombre y los tipos.
- **Comentarios:** explican el porqué (regla de negocio, restricción, unidad, zona horaria), nunca el qué.
