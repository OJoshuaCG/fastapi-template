#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint del contenedor
#
#   serve    (default) inicia la API.
#   <otro>   ejecuta el comando tal cual (ej: docker compose run --rm api python -V)
#
# El esquema de la BD se administra con scripts SQL en database/ (ver database/README.md).
# ─────────────────────────────────────────────────────────────────────────────
set -eu

serve() {
    workers="${WORKERS:-1}"

    if [ "$workers" -gt 1 ] && [ "${RATE_LIMIT_REDIS_ENABLED:-False}" != "True" ] \
        && [ "${RATE_LIMIT_REDIS_ENABLED:-false}" != "true" ]; then
        echo "[entrypoint] AVISO: $workers workers con rate limit en memoria: cada worker cuenta por separado."
    fi

    echo "[entrypoint] Iniciando API con $workers worker(s)..."
    # exec: uvicorn queda como PID 1 y recibe SIGTERM para el apagado ordenado.
    # --forwarded-allow-ips: SOLO la IP/red del proxy. Con "*" cualquier cliente podría
    #   falsificar su IP con X-Forwarded-For (y saltarse el rate limit).
    # --timeout-graceful-shutdown: debe ser menor que el grace period del orquestador
    #   (stop_grace_period en compose) para que el lifespan alcance a cerrar el pool.
    exec uvicorn main:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" \
        --workers "$workers" \
        --proxy-headers \
        --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
        --timeout-graceful-shutdown "${GRACEFUL_TIMEOUT:-8}" \
        --no-access-log \
        --no-server-header
}

case "${1:-serve}" in
    serve)
        serve
        ;;
    *)
        exec "$@"
        ;;
esac
