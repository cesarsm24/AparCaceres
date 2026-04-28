"""Rate limiting global con `slowapi`.

slowapi es el port de Flask-Limiter a Starlette/FastAPI: decora rutas
concretas (`@limiter.limit("N/minute")`) y devuelve `429 Too Many Requests`
cuando el cliente excede el cupo.

Decisiones:
- Backend Redis compartido por defecto: el cupo se cuenta de forma global
  entre todos los workers de uvicorn. Sin esto, dos workers duplicarían
  silenciosamente el cupo efectivo. Si Redis no está disponible al arrancar,
  slowapi cae a in-memory automáticamente (degradación grácil).
- `key_func=get_remote_address` cuenta por IP. Cuando el servicio corre tras
  nginx/Traefik con `--proxy-headers`, Starlette lee `X-Forwarded-For` y la
  IP real llega correctamente. Sin proxy honesto, el limiter cae al peer
  TCP, que sigue siendo aceptable para el alcance actual.
- `enabled` controlable por entorno (`RATE_LIMIT_ENABLED=false` en tests para
  evitar interferencias entre casos). El default en producción es `True`.

Las rutas concretas decoran con su límite específico. No se establece un
default global porque endpoints como `/healthz` deben ser libres para que el
loadbalancer los pinche con la frecuencia que quiera.
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import REDIS_DB, REDIS_HOST, REDIS_PORT


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


RATE_LIMIT_ENABLED = _env_flag("RATE_LIMIT_ENABLED", True)

# `RATE_LIMIT_STORAGE_URI` permite forzar otro backend en tests/CI o usar un
# Redis dedicado distinto del catálogo. Por defecto reusamos el mismo Redis
# del servicio para no añadir infraestructura.
RATE_LIMIT_STORAGE_URI = os.getenv(
    "RATE_LIMIT_STORAGE_URI",
    f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
)


limiter = Limiter(
    key_func=get_remote_address,
    enabled=RATE_LIMIT_ENABLED,
    headers_enabled=True,
    storage_uri=RATE_LIMIT_STORAGE_URI,
)


# Cupos publicados en un único sitio para que las rutas los importen y los
# tests los puedan referenciar sin hardcodear strings.
RATE_LIMIT_IMPORT = "1/minute"        # /import-parkings: operación cara, no debería repetirse.
RATE_LIMIT_NEARBY = "120/minute"      # /parkings/nearby: uso activo del mapa, holgado.
