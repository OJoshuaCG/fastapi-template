# ─────────────────────────────────────────────────────────────────────────────
# Builder: instala dependencias con uv
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

# uv con versión fija (build reproducible); solo existe en esta etapa
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Extras opcionales, ej: docker build --build-arg UV_EXTRAS="--extra redis" .
ARG UV_EXTRAS=""

# 1) Dependencias (capa cacheada mientras pyproject.toml/uv.lock no cambien)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project ${UV_EXTRAS}

# 2) Código del proyecto
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev ${UV_EXTRAS} \
    && chmod +x docker/scripts/entrypoint.sh


# ─────────────────────────────────────────────────────────────────────────────
# Production: imagen mínima, sin uv ni curl, usuario sin privilegios
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim AS production

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /usr/sbin/nologin --no-create-home app

WORKDIR /app
# Código y venv propiedad de root (no escribibles en runtime); solo uploads/ es del usuario app
COPY --from=builder /app /app
RUN mkdir -p /app/uploads && chown app:app /app/uploads

USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WORKERS=1 \
    GRACEFUL_TIMEOUT=8 \
    FORWARDED_ALLOW_IPS=127.0.0.1

EXPOSE 8000

# Healthcheck en Python puro (sin instalar curl). /health no depende de la BD.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["/app/docker/scripts/entrypoint.sh"]
CMD ["serve"]
