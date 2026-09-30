# CORS

`CORSMiddleware` de Starlette está en la **app raíz** (`main.py`). Cubre todas las versiones y también `/health` y `/ready`.

## Configuración

```env
# Orígenes separados por coma. Vacío = CORS deshabilitado (no se agrega el middleware).
CORS_ORIGINS=http://localhost:3000,https://app.example.com
```

`Settings` separa la lista por comas y quita los espacios. `CORS_ALLOW_CREDENTIALS` vale `True` por defecto; la app usa la propiedad derivada `settings.cors_allow_credentials`, que es `False` si `CORS_ORIGINS` contiene `*`.

## Configuración aplicada

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
```

- `expose_headers` permite que el frontend lea `X-Request-ID` (para reportar errores) y `Retry-After` (rate limit, 503).
- Si tu frontend envía otros headers, agrégalos a `allow_headers` en `create_app()`.

## `*`

```env
CORS_ORIGINS=*
```

- Con `*` se fuerza `allow_credentials=False`. Con `*` y credenciales, Starlette refleja cualquier `Origin`, y eso equivale a acceso abierto con cookies.
- En `APP_ENV=production`, `*` es **error de configuración** y la app no arranca.

En producción, lista los orígenes exactos.

## Posición en el stack

```
ContextMiddleware → LoggerMiddleware → CORSMiddleware → rutas / sub-apps
```

Los preflight `OPTIONS` se responden en CORS, antes de llegar a las sub-apps. Por eso no consumen rate limit ni pasan por el límite de body. Igual quedan en el access log y llevan `X-Request-ID`.

## Verificar

```bash
curl -i -X OPTIONS http://localhost:8000/api/v1/test/ping \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST"
# access-control-allow-origin: http://localhost:3000
```

Un origen no listado no recibe `access-control-allow-origin`.

---

Ver también: [Middlewares](middlewares.md)
