import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ (raíz del servicio). Usamos __file__ para que las rutas funcionen sea cual
# sea el cwd desde el que se lance uvicorn.
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Carga variables desde backend/.env si existe.
load_dotenv(BACKEND_DIR / ".env")

# Dataset GeoJSON con los aparcamientos públicos de Cáceres (Open Data).
DATA_FILE = BACKEND_DIR / "data" / "aparcamientos.geojson"

# Claves de Redis que usa la app:
#   geo:parkings                       -> sorted set geoespacial (GEOADD / GEOSEARCH)
#   parking:{id}                       -> hash con metadatos del aparcamiento (HSET / HGETALL)
#   cache:nearby:{lat}:{lng}:{radius}  -> JSON cacheado del resultado de /parkings/nearby (SETEX)
GEO_KEY = "geo:parkings"
PARKING_KEY_PREFIX = "parking:"
CACHE_NEARBY_PREFIX = "cache:nearby:"

# ---------- Config leída del entorno / .env (defaults para dev) ----------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
# CORS_ORIGINS: lista separada por comas. "*" = cualquier origen (solo dev).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
# TTL de la caché de /parkings/nearby en segundos. 0 = caché desactivada.
CACHE_NEARBY_TTL = int(os.getenv("CACHE_NEARBY_TTL", "60"))
