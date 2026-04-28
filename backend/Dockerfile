# syntax=docker/dockerfile:1.7
# Imagen runtime del backend FastAPI de AparCáceres.
# Usa build multi-stage para separar la instalación de dependencias del
# contenedor final y evitar incluir cachés o herramientas innecesarias.

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt


FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_ENV=production \
    LOG_LEVEL=INFO

# Dependencia mínima necesaria para ejecutar el healthcheck del contenedor.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# UID/GID fijos para que permisos y volúmenes montados sean reproducibles.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=app:app main.py ./
COPY --chown=app:app app ./app
COPY --chown=app:app data ./data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]