"""Rate limiting global con `slowapi`.

slowapi es el port de Flask-Limiter a Starlette/FastAPI: decora rutas
concretas (`@limiter.limit("N/minute")`) y devuelve `429 Too Many Requests`
cuando el cliente excede el cupo.

Decisiones:
- Backend in-memory por defecto. En despliegues multi-worker conviene mover
  a Redis (`storage_uri="redis://..."`) para que el cupo se comparta entre
  procesos. Se prefiere mantenerlo simple en esta fase: una sola réplica del
  backend basta para staging.
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


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


RATE_LIMIT_ENABLED = _env_flag("RATE_LIMIT_ENABLED", True)


# Almacenamiento por defecto: in-memory. Para multi-worker, sustituir por
# `storage_uri=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"`.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=RATE_LIMIT_ENABLED,
    headers_enabled=True,
)


# Cupos publicados en un único sitio para que las rutas los importen y los
# tests los puedan referenciar sin hardcodear strings.
RATE_LIMIT_IMPORT = "1/minute"        # /import-parkings: operación cara, no debería repetirse.
RATE_LIMIT_NEARBY = "120/minute"      # /parkings/nearby: uso activo del mapa, holgado.
