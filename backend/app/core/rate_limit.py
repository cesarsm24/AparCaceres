"""Rate limiting compartido para rutas FastAPI.

Configura `slowapi` con clave por dirección remota y almacenamiento Redis para
mantener cupos coherentes entre workers. El límite se habilita por defecto y
puede desactivarse mediante `RATE_LIMIT_ENABLED=false`, especialmente en tests.
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import REDIS_DB, REDIS_HOST, REDIS_PORT


def _env_flag(name: str, default: bool) -> bool:
    """Interpreta una variable de entorno como valor booleano."""
    raw = os.getenv(name)
    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


RATE_LIMIT_ENABLED = _env_flag("RATE_LIMIT_ENABLED", True)

# Permite usar un backend específico para rate limiting sin acoplarlo al Redis
# principal del catálogo.
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

# Cupos compartidos entre routers y tests para evitar literales duplicados.
RATE_LIMIT_IMPORT = "1/minute"
RATE_LIMIT_NEARBY = "120/minute"