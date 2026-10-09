# Iniciar un proyecto desde la plantilla

La plantilla trae código de ejemplo (`users`, `httpbin`, endpoints `/api/v1/test/*`). Parte de ese código también
sirve como **banco de pruebas de la infraestructura**: borrarlo sin adaptar los tests rompe la suite.

## 1. Configuración propia

- `cp .env.example .env` y revisar las variables sin comentar.
- `APP_NAME` del proyecto.
- `ENCODING_ALPHABET` propio y **fijo para siempre** (cambiarlo invalida los IDs ya compartidos); cómo generarlo en
  [deployment.md](../deployment.md).
- `ENCRYPTION_KEYS` y `SECRET_KEY` nuevos, distintos entre sí (ver [configuration.md](configuration.md)).

## 2. Qué es ejemplo y qué depende de él

| Pieza de ejemplo | Archivos | Quién la usa además del ejemplo |
|---|---|---|
| CRUD de usuarios | `app/models/user_model.py`, `app/controllers/user_controller.py`, `app/schemas/user.py`, `app/routes/v1/users.py`, `database/init/001_users.sql` | `tests/test_users_api.py`; `tests/test_database.py` y la fixture `clean_users` (`tests/conftest.py`) usan la tabla `users`; `tests/test_http.py` usa `/api/v1/users` para el límite de body |
| Stored procedure | `database/procedures/sp_user_stats.sql` | `tests/test_database.py` (prueba de `call_procedure`) |
| Integración externa | `app/services/httpbin_service.py` | `app/routes/v1/test.py` (`/test/external/echo`), `tests/test_http_client.py` |
| Endpoints de diagnóstico | `app/routes/v1/test.py` (no se registra en producción) | `tests/test_http.py` (request id, errores, validación, uploads, rate limit, streaming) |

## 3. Recomendación

- **Conservar** `app/routes/v1/test.py`: no se publica en producción y es lo que prueba los middlewares, errores y
  límites. Si se elimina, reescribir `tests/test_http.py` contra endpoints propios.
- **Reemplazar `users` cuando exista la primera entidad real**, no antes: al borrarla, mover `tests/test_database.py`
  y la fixture `clean_users` a esa tabla, y quitar `users` de `app/routes/v1/routes.py`.
- **Reemplazar `httpbin`** por el primer service real; mientras tanto puede quedar (no se llama si nadie usa `/test/external/echo`).
- Si un proyecto ya usa la tabla `users` con otra forma, crear su propio script `database/init/` en lugar de editar
  `001_users.sql` cuando ya se aplicó en algún entorno.

## 4. Al terminar

- Quitar del `.env.example` y de `Settings` las variables de integraciones que no se usen (y sus tests).
- Actualizar `readme.md` y `docs/` con el dominio del proyecto: la lógica de negocio propia se documenta en `docs/`.
- Verificar con los comandos de [testing-and-quality.md](testing-and-quality.md).
