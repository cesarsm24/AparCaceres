"""Configuración central del servicio.

Agrupa rutas, claves Redis y parámetros de ejecución leídos desde variables
de entorno o desde `backend/.env`. La capa valida al arrancar los valores que
no pueden quedar implícitos en producción y expone el resto como constantes
compartidas por routers, importador y cliente Redis.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"

PARKING_KEY_PREFIX = "parking:"
SEARCH_INDEX_NAME = "idx:parkings_search"

# Prefijo e índice de staging usados por el importador para construir una nueva
# generación de datos antes de sustituir la activa.
STAGING_KEY_PREFIX = "parking_v2:"
STAGING_INDEX_NAME = "idx:parkings_search_v2"

CACHE_NEARBY_PREFIX = "cache:nearby:"
CACHE_VERSION_KEY = "cache:version"
USER_FAVORITES_KEY_PREFIX = "user:"
USER_FAVORITES_KEY_SUFFIX = ":favorites"

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

_CORS_RAW = os.getenv("CORS_ORIGINS")
_CORS_ENV = os.getenv("APP_ENV", "production").strip().lower()
_DEV_DEFAULT_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:5000,http://127.0.0.1:5000,"
    "http://localhost:8080,http://127.0.0.1:8080"
)

if _CORS_RAW is None:
    _CORS_RAW = _DEV_DEFAULT_ORIGINS if _CORS_ENV in {"dev", "development", "local"} else ""

CORS_ORIGINS = [origin.strip() for origin in _CORS_RAW.split(",") if origin.strip()]
CORS_ALLOW_ALL = CORS_ORIGINS == ["*"]


def _looks_like_example_value(value: str) -> bool:
    """Detecta valores de plantilla que no deben usarse como secretos reales.

    Evita que un `.env` copiado del ejemplo llegue a producción sin reemplazar
    los marcadores angulares.
    """
    return value.startswith("<") and value.endswith(">")


if _CORS_ENV == "production":
    if not CORS_ORIGINS:
        raise RuntimeError("CORS_ORIGINS debe definirse en producción")
    if CORS_ALLOW_ALL:
        raise RuntimeError("CORS_ORIGINS no puede ser '*' en producción")

CACHE_NEARBY_TTL = int(os.getenv("CACHE_NEARBY_TTL", "60"))

IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "").strip()
if _CORS_ENV == "production":
    if not IMPORT_TOKEN:
        raise RuntimeError("IMPORT_TOKEN debe definirse en producción")
    if _looks_like_example_value(IMPORT_TOKEN):
        raise RuntimeError("IMPORT_TOKEN debe reemplazar el valor de ejemplo")

DEFAULT_PARKING_LIMIT = int(os.getenv("DEFAULT_PARKING_LIMIT", "100"))
MAX_PARKING_LIMIT = int(os.getenv("MAX_PARKING_LIMIT", "500"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

if _CORS_ENV == "production":
    favorites_secret = os.getenv("FAVORITES_SECRET", "").strip()
    if not favorites_secret:
        raise RuntimeError("FAVORITES_SECRET debe definirse en producción")
    if _looks_like_example_value(favorites_secret):
        raise RuntimeError("FAVORITES_SECRET debe reemplazar el valor de ejemplo")

# La resolución de fotos hace scraping de fichas municipales durante el import
# cuando el dataset no trae una URL directa.
FETCH_PHOTOS = os.getenv("FETCH_PHOTOS", "true").strip().lower() in {
    "1", "true", "yes", "on",
}
PHOTO_FETCH_CONCURRENCY = int(os.getenv("PHOTO_FETCH_CONCURRENCY", "20"))
PHOTO_FETCH_TIMEOUT_SECONDS = float(os.getenv("PHOTO_FETCH_TIMEOUT_SECONDS", "5.0"))

# Las fotos cambian con poca frecuencia; el TTL evita reconsultas masivas en
# importaciones sucesivas sin bloquear actualizaciones editoriales futuras.
PHOTO_CACHE_TTL_SECONDS = int(
    os.getenv("PHOTO_CACHE_TTL_SECONDS", str(60 * 60 * 24 * 90))
)
PHOTO_CACHE_KEY_PREFIX = "parking_photo:"

# Caché local del proxy de fotos. Se usa para miniaturas generadas a partir de
# imágenes públicas del SIG y se monta como volumen en Docker Compose.
PHOTO_PROXY_CACHE_DIR = Path(
    os.getenv("PHOTO_PROXY_CACHE_DIR", "/app/photo-cache")
)
PHOTO_THUMBNAIL_MAX_SIZE = int(os.getenv("PHOTO_THUMBNAIL_MAX_SIZE", "180"))

# Tope defensivo para evitar crecimiento indefinido del sorted set por usuario.
FAVORITES_MAX_PER_USER = int(os.getenv("FAVORITES_MAX_PER_USER", "500"))

# TTL renovado en cada alta de favorito para conservar cuentas activas.
FAVORITES_TTL_SECONDS = int(os.getenv("FAVORITES_TTL_SECONDS", str(60 * 60 * 24 * 365)))
