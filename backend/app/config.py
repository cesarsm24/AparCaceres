from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ (raíz del servicio). Usamos __file__ para que las rutas funcionen sea cual
# sea el cwd desde el que se lance uvicorn.
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Carga variables desde backend/.env si existe.
load_dotenv(BACKEND_DIR / ".env")

# Directorio con los datasets GeoJSON de Open Data Cáceres. El importador
# procesa todos los `*.geojson` del directorio y normaliza cada fichero
# contra el contrato móvil, infiriendo categoría/vehículo/régimen del
# filename cuando el feature no los aporta.
DATA_DIR = BACKEND_DIR / "data"

# Claves de Redis que usa la app:
#   parking:{id}                              -> hash con metadatos del aparcamiento (HSET / HGETALL)
#   parking_v2:{id}                           -> staging del importador con doble buffer
#   idx:parkings_search                       -> índice RediSearch sobre hashes parking:*
#   idx:parkings_search_v2                    -> índice de staging del importador
#   cache:nearby:v{n}:{lat}:{lng}:{radius}    -> JSON cacheado del resultado de /parkings/nearby (SETEX)
#   cache:version                             -> entero monotónico que namespacia las claves de caché
#   user:{user_id}:favorites                  -> sorted set con ids favoritados, score = epoch ms (ZREVRANGE para newest-first)
PARKING_KEY_PREFIX = "parking:"
SEARCH_INDEX_NAME = "idx:parkings_search"
# Doble buffer para imports sin downtime: el importador construye la nueva
# generación bajo el prefijo de staging y, una vez completa, hace el swap
# (drop índice activo + UNLINK activo + RENAME staging → activo +
# recrear índice).
STAGING_KEY_PREFIX = "parking_v2:"
STAGING_INDEX_NAME = "idx:parkings_search_v2"
CACHE_NEARBY_PREFIX = "cache:nearby:"
CACHE_VERSION_KEY = "cache:version"
USER_FAVORITES_KEY_PREFIX = "user:"
USER_FAVORITES_KEY_SUFFIX = ":favorites"

# Filenames que el importador NUNCA procesa, aunque estén físicamente en
# `backend/data/`. `parkings_en_superficie.geojson` queda fuera porque sus
# 15.000+ LineStrings con `properties: {}` no aportan datos accionables y
# saturarían los índices y respuestas de la API.
EXCLUDED_DATASET_FILENAMES: frozenset[str] = frozenset({
    "parkings_en_superficie.geojson",
})

# ---------- Config leída del entorno / .env (defaults para dev) ----------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# CORS_ORIGINS: lista separada por comas con los orígenes permitidos. El
# default es la lista vacía (CORS cerrado) para que producción nunca se exponga
# a `*` por accidente. En desarrollo se sirve un default ergonómico cuando la
# variable se deja sin definir.
#
# El cliente nativo Android/iOS no envía `Origin`, así que CORS no le afecta.
# Solo hace falta declarar orígenes para Flutter web (`flutter run -d chrome`)
# y para cualquier panel web futuro. Valores aceptados:
#   - lista explícita: "https://aparcaceres.app,https://staging.aparcaceres.app"
#   - "*"             -> permite cualquier origen (solo dev; nunca producción).
#   - vacío           -> CORS deshabilitado (no se añaden cabeceras).
_CORS_RAW = os.getenv("CORS_ORIGINS")
_CORS_ENV = os.getenv("APP_ENV", "production").strip().lower()
_DEV_DEFAULT_ORIGINS = (
    # Puertos típicos del runner de Flutter web en dev (`--web-port` aleatorio
    # por defecto, los más comunes en plantillas son 3000, 5000, 8080).
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:5000,http://127.0.0.1:5000,"
    "http://localhost:8080,http://127.0.0.1:8080"
)
if _CORS_RAW is None:
    _CORS_RAW = _DEV_DEFAULT_ORIGINS if _CORS_ENV in {"dev", "development", "local"} else ""
CORS_ORIGINS = [o.strip() for o in _CORS_RAW.split(",") if o.strip()]
# `*` solo tiene sentido cuando se usa solo (no se mezcla con orígenes concretos).
CORS_ALLOW_ALL = CORS_ORIGINS == ["*"]

# TTL de la caché de /parkings/nearby en segundos. 0 = caché desactivada.
CACHE_NEARBY_TTL = int(os.getenv("CACHE_NEARBY_TTL", "60"))
# Token requerido para `POST /import-parkings`. Si está vacío, el endpoint
# acepta cualquier petición (útil en desarrollo). En producción conviene fijar
# un valor en el .env y enviar `X-Import-Token` desde el cliente que reimporta.
IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "").strip()
# Límite duro por defecto en endpoints que pueden devolver muchos resultados.
# El cliente puede subirlo hasta MAX_PARKING_LIMIT con el query param `limit`.
DEFAULT_PARKING_LIMIT = int(os.getenv("DEFAULT_PARKING_LIMIT", "100"))
MAX_PARKING_LIMIT = int(os.getenv("MAX_PARKING_LIMIT", "500"))
# Nivel de logging raíz del proceso. Se aplica desde `main.py` vía
# `configure_logging(LOG_LEVEL)`.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------- Favoritos por usuario ----------
# Tope superior de favoritos por usuario. Cuando el usuario añade uno nuevo y
# ya tiene >= MAX, el más antiguo se elimina con `ZREMRANGEBYRANK`. 0 desactiva
# el cap (no recomendado en producción).
FAVORITES_MAX_PER_USER = int(os.getenv("FAVORITES_MAX_PER_USER", "500"))
# TTL en segundos del sorted set de favoritos por usuario. Se renueva en cada
# `PUT` para que las cuentas activas no expiren. 0 desactiva el TTL.
FAVORITES_TTL_SECONDS = int(os.getenv("FAVORITES_TTL_SECONDS", str(60 * 60 * 24 * 365)))
