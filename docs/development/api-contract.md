# Contrato de la API

Reglas que **todos** los endpoints respetan, para que un cliente que aprendió un endpoint ya sepa usar los demás.
Si un endpoint necesita salirse de una regla, se documenta como excepción en el propio endpoint (OpenAPI) y aquí.

Complementa: [api-conventions.md](api-conventions.md) (helpers de respuesta y errores), `docs/features/pagination.md`
y `docs/features/exceptions.md`.

## 1. Dónde va cada dato

| Ubicación | Qué lleva | Ejemplo | Nunca |
|---|---|---|---|
| **Path** | Solo el identificador del recurso (`EncodedId`) | `GET /api/v1/users/Xk3pQ9aL` | Filtros, orden, paginación, acciones como verbos |
| **Query** | Lectura: paginación, filtros, orden, búsqueda | `GET /api/v1/users?is_active=true&sort=-created_at` | Datos a escribir, secretos o datos personales |
| **Body (JSON)** | Escritura: `POST`, `PUT`, `PATCH` | `PATCH /api/v1/users/Xk3pQ9aL {"full_name": "Ana"}` | Body en `GET`/`DELETE` |
| **Headers** | Transversal: `Authorization`, `X-Request-ID`, `Idempotency-Key` | `X-Request-ID: a1b2c3d4` | Datos de negocio |

- Los query params quedan en logs de nginx y del proxy: **nunca** tokens, contraseñas ni datos personales en la URL.
  Una búsqueda por email o documento va por `POST /recurso/search` con body.
- Excepción permitida: `POST /recurso/search` con body cuando los filtros no caben razonablemente en la URL
  (listas largas, estructuras anidadas). Responde igual que el `GET` de listado (paginado, mismo `sort`).

## 2. Nombres y URLs

- Recursos en **plural** y `kebab-case`: `/users`, `/purchase-orders`. Sub-recursos solo para pertenencia real:
  `/orders/{order_id}/items`.
- Parámetros (query) y campos (body y respuesta) en **`snake_case`**: `is_active`, `created_at`.
- Una acción que no es CRUD se expresa como sub-recurso con `POST`: `POST /orders/{order_id}/cancellation`.
- Un mismo concepto se llama igual en todos los endpoints (`created_at`, no `fecha_alta` en uno y `created` en otro).

## 3. Métodos y status

| Operación | Método | Éxito | Respuesta |
|---|---|---|---|
| Listar | `GET /recurso` | 200 | `paginated(...)` (siempre paginado) |
| Obtener uno | `GET /recurso/{id}` | 200 | `success(data=...)` |
| Crear | `POST /recurso` | 201 | `success(data=<recurso creado>, message=...)` |
| Actualizar parcial | `PATCH /recurso/{id}` | 200 | `success(data=<recurso actualizado>)` |
| Reemplazar completo | `PUT /recurso/{id}` | 200 | Solo si el caso lo pide; por defecto `PATCH` |
| Eliminar | `DELETE /recurso/{id}` | 200 | `empty(message=...)` |

- `PATCH` actualiza solo los campos enviados (`model_dump(exclude_unset=True)`); enviar `null` en un campo obligatorio es 422.
- Errores: 404 recurso inexistente (o id inválido), 409 conflicto o regla de negocio, 413/415 archivo, 422 validación,
  429 rate limit. Formato único `{"detail": {...}}` ([exceptions](../features/exceptions.md)).

## 4. Paginación

- `?page=1&size=20`. `page ≥ 1` (máx. 1 000 000), `1 ≤ size ≤ PAGINATION_MAX_SIZE`. Fuera de rango: 422.
- **Todo listado es paginado**: no hay endpoints que devuelvan una colección sin límite.
- Respuesta: `{"data": [...], "pagination": {"page", "size", "total", "pages", "has_next", "has_prev"}}`.
- Nunca `limit`/`offset` en la URL. Cursor solo como excepción ([pagination](../features/pagination.md)).

## 5. Ordenamiento

Un solo parámetro `sort`, con la lista de campos separados por coma; el prefijo `-` indica descendente:

```http
GET /api/v1/users?sort=-created_at          # más recientes primero
GET /api/v1/users?sort=username,-created_at # username asc, luego created_at desc
```

- Solo campos de una **whitelist por endpoint** (nombre público → columna SQL). Campo no permitido: 422 que lista
  los válidos (`invalid_sort`). Nunca se interpola el valor recibido en el SQL.
- Máximo 3 campos. Sin `sort`, cada endpoint aplica y documenta su orden por defecto (habitualmente `-created_at`).
- El SQL siempre agrega `id` como desempate final, para que la paginación sea estable (sin filas repetidas ni
  perdidas entre páginas).

## 6. Filtros

| Tipo | Forma | Ejemplo | Semántica |
|---|---|---|---|
| Igualdad | `campo=valor` | `?is_active=true` | `campo = valor` |
| Varios valores | parámetro repetido | `?status=active&status=pending` | `campo IN (...)`; máx. 50 valores (`MAX_FILTER_VALUES`) |
| Booleano | `true` / `false` | `?is_active=false` | Valores canónicos; no usar `1`/`0` |
| Rango numérico | `campo_min`, `campo_max` | `?amount_min=1000&amount_max=5000` | Ambos inclusivos; `min > max` = 422 |
| Rango de fechas | `campo_from`, `campo_to` | `?created_at_from=2026-01-01&created_at_to=2026-01-31` | Ver §7 |
| Texto libre | `q` | `?q=ana` | Busca en columnas documentadas del endpoint; 2–100 caracteres |
| Referencia a otro recurso | `recurso_id` | `?user_id=Xk3pQ9aL` | `EncodedId`, nunca el int crudo |

- Todos los filtros se combinan con **AND**. Un filtro omitido no filtra.
- El `WHERE` se arma **una sola vez** y se usa en el listado y en el `count`, para que `total` sea coherente
  (ver `UserModel._filters()`).
- `q` escapa `%` y `_` antes del `LIKE`; el endpoint documenta si busca por prefijo (usa índice) o contenido.
- **Parámetros desconocidos: 422** (`extra_forbidden`). Un typo (`?is_activ=true`) no debe devolver todo sin filtrar.
- Montos: enteros en unidad mínima (centavos) o decimales como string (`"1250.50"`), nunca float.

## 7. Fechas y horas

**Formato (ISO 8601, sin zona horaria):**

- Fecha: `YYYY-MM-DD` → `2026-10-09`.
- Fecha y hora: `YYYY-MM-DDTHH:MM:SS` → `2026-10-09T14:30:00` (segundos y fracción opcionales).
- Con zona (`Z`, `-06:00`): 422 `date_filter_timezone`. Las fechas se comparan tal como están guardadas; la
  conversión a la hora del usuario la hace el cliente.

**Filtros por fecha:** dos parámetros por campo, `<campo>_from` y `<campo>_to`, **ambos inclusivos**. Cubren todos
los casos:

| Caso | Solicitud |
|---|---|
| Un día específico | `?created_at_from=2026-10-09&created_at_to=2026-10-09` |
| Rango | `?created_at_from=2026-10-01&created_at_to=2026-10-31` |
| Desde una fecha | `?created_at_from=2026-10-01` |
| Hasta una fecha | `?created_at_to=2026-10-31` |
| Rango con hora | `?created_at_from=2026-10-09T08:00:00&created_at_to=2026-10-09T18:00:00` |

- Con solo fecha (`YYYY-MM-DD`), `_to` incluye el **día completo**. En SQL se traduce a un intervalo semiabierto, que
  usa índices y no depende de `23:59:59`: `created_at >= :from AND created_at < :día_siguiente`.
- Con fecha y hora, `_to` es exacto: `2026-10-09T00:00:00` es la medianoche, **no** el día completo.
- `_from` posterior a `_to`: 422 `invalid_range`. Cada endpoint puede fijar un rango máximo (ej. 366 días) y lo documenta.

## 8. Respuestas

- Siempre `ApiResponse[T]` con `success()`, `paginated()` o `empty()`; `response_model` explícito.
- Los campos de `data` aparecen siempre, con `null` si no tienen valor (no se omiten).
- IDs como `EncodedIdOut` (string). Nunca columnas sensibles (contraseñas, llaves, tokens).
- Un listado sin resultados es 200 con `data: []`, no 404.

## 9. Escrituras seguras

- Body con `extra="forbid"`: un campo desconocido es 422.
- La unicidad la decide el índice `UNIQUE` (409 `duplicate`), no un `SELECT` previo.
- Operaciones que no deben repetirse (pagos, envíos) aceptan el header `Idempotency-Key` y devuelven el mismo
  resultado si se reintentan con la misma llave.

## 10. Versionado y cambios

- Compatible dentro de la misma versión (`/api/v1`): agregar endpoints, parámetros opcionales o campos de respuesta.
- Rompe el contrato y va en una versión nueva (`/api/v2`): quitar o renombrar campos o parámetros, cambiar tipos,
  formatos o semántica, volver obligatorio algo opcional.

## 11. Errores del contrato

Todo parámetro fuera del contrato responde **422** con `code: "validation_error"` y un elemento por problema en
`errors`, con `field` (el nombre del parámetro), `message` (en español, sin el valor enviado) y un `type` estable que
el frontend puede usar:

| `type` | Cuándo |
|---|---|
| `extra_forbidden` | Parámetro que el endpoint no declara (typo o filtro inexistente) |
| `invalid_sort` | `sort` con un campo no permitido, vacío, repetido, más de 3 campos, o en un listado sin orden |
| `invalid_range` | `<campo>_to` anterior a `<campo>_from`, o `<campo>_max` menor que `<campo>_min` |
| `date_filter_format` | Fecha que no es `YYYY-MM-DD` ni `YYYY-MM-DDTHH:MM:SS`, o fecha inexistente (`2026-02-30`) |
| `date_filter_timezone` | Fecha y hora con zona (`Z`, `-06:00`) |
| `string_too_short` / `string_too_long` | `q` fuera de 2–100 caracteres |
| `too_long` | Filtro repetido con más de 50 valores |
| `greater_than_equal` / `less_than_equal` | `page` o `size` fuera de rango |
| `literal_error`, `bool_parsing`, `int_parsing`... | Valor que no corresponde al tipo del filtro |

```json
{"detail": {
  "msg": "Error de validación: sort no admite password; campos permitidos: created_at, username, email",
  "type": "ValidationError",
  "code": "validation_error",
  "errors": [{"field": "sort", "message": "no admite password; campos permitidos: created_at, username, email",
              "type": "invalid_sort"}],
  "request_id": "a1b2c3d4e5f60708"
}}
```

## Checklist de un endpoint nuevo

- [ ] Path con recurso en plural y solo el id; filtros, orden y paginación en query.
- [ ] Listado con un modelo que hereda de `ListQuery`, recibido con `Annotated[XxxListQuery, Query()]` (nada de
      query params sueltos al lado: `tests/test_architecture.py` lo rechaza).
- [ ] `sortable_fields` y `default_sort` en el schema; la misma whitelist (nombre → columna) en el model.
- [ ] Filtros con los nombres de §6 y §7 (`DateFilter`, `SearchText`, `max_length=MAX_FILTER_VALUES`); `_from` antes de `_to`.
- [ ] SQL con `WhereBuilder` y `order_by` (`app/core/sql_filters.py`); el mismo `WHERE` en el listado y el `count`.
- [ ] `response_model=ApiResponse[T]`, status de §3, errores con `AppHttpException` y `code` estable.
- [ ] Descripción de cada parámetro en OpenAPI (`Field(description=...)`).

## Soporte en la plantilla

| Regla del contrato | Soporte | Dónde |
|---|---|---|
| `page` / `size` (§4) | ✅ | `ListQuery` (`app/utils/list_query.py`) |
| `sort` con whitelist y desempate (§5) | ✅ | `ListQuery.sortable_fields` / `sort_terms` + `order_by()` (`app/core/sql_filters.py`) |
| Rechazo de parámetros desconocidos (§6) | ✅ en listados | `ListQuery` (`extra="forbid"`) |
| Igualdad, varios valores (IN), rangos numéricos (§6) | ✅ | `WhereBuilder.equals` / `any_of` / `number_range`; validación `_min`/`_max` en `ListQuery` |
| Búsqueda `q` con `LIKE` escapado (§6) | ✅ | `SearchText` + `WhereBuilder.contains_text` |
| Rangos de fecha `_from`/`_to` (§7) | ✅ | `DateFilter` + `WhereBuilder.date_range`; validación en `ListQuery` |
| IDs en filtros (`?user_id=`) | ⚠️ sin ejemplo ni test | Declarar el campo con tipo `EncodedId` (`app/core/encoding.py`) |
| Errores del contrato con `type` estable (§11) | ✅ | Handler de 422 (`app/exceptions/HandlerExceptions.py`) |
| Ejemplo completo | ✅ | `GET /api/v1/users` (`UserListQuery`, `UserModel._filters()`) |
| Obligatorio en todo listado | ✅ | `tests/test_architecture.py`: un `GET` con `ApiResponse[list[...]]` debe recibir exactamente un modelo `ListQuery` |
| Rechazo de parámetros desconocidos fuera de listados (`GET /{id}`, `POST`...) | ❌ | FastAPI los ignora; un endpoint que lo necesite declara su propio modelo de query con `extra="forbid"` |
| `POST /recurso/search` (§1) | ❌ sin helper | Body con un schema que reutilice los mismos tipos (`DateFilter`, `SearchText`) |
| `Idempotency-Key` (§9) | ❌ | Se implementa por endpoint cuando aparezca el caso (pagos, envíos) |
| Zonas horarias | Fuera de alcance | Fechas sin zona; la conversión a la hora del usuario la hace el cliente |
