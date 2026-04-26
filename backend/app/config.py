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
# procesa todos los `*.geojson` del directorio y normaliza cada fichero contra
# el contrato móvil, infiriendo categoría/vehículo/régimen del filename
# cuando el feature no los aporta. Mantenemos `DATA_FILE` para compatibilidad
# con cualquier herramienta que aún apunte al fichero original.
DATA_DIR = BACKEND_DIR / "data"
DATA_FILE = DATA_DIR / "aparcamientos.geojson"

# Claves de Redis que usa la app:
#   geo:parkings                       -> sorted set geoespacial (GEOADD / GEOSEARCH)
#   parking:{id}                       -> hash con metadatos del aparcamiento (HSET / HGETALL)
#   idx:parkings_search                -> índice RediSearch sobre hashes parking:*
#   cache:nearby:{lat}:{lng}:{radius}  -> JSON cacheado del resultado de /parkings/nearby (SETEX)
#   user:{user_id}:favorites           -> sorted set con ids favoritados, score = epoch ms (ZREVRANGE para newest-first)
GEO_KEY = "geo:parkings"
PARKING_KEY_PREFIX = "parking:"
SEARCH_INDEX_NAME = "idx:parkings_search"
CACHE_NEARBY_PREFIX = "cache:nearby:"
USER_FAVORITES_KEY_PREFIX = "user:"
USER_FAVORITES_KEY_SUFFIX = ":favorites"
# Prefijo legacy: se limpia al reimportar para migrar bases con índices Redis
# SET antiguos, pero las consultas nuevas usan RediSearch.
INDEX_KEY_PREFIX = "idx:"

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
# CORS_ORIGINS: lista separada por comas. "*" = cualquier origen (solo dev).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
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
# Ventana máxima de documentos que el backend traerá de RediSearch para ordenar
# por distancia cuando Redis no proporciona sort nativo por distancia.
MAX_SEARCH_WINDOW = int(os.getenv("MAX_SEARCH_WINDOW", "5000"))
