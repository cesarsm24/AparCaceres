import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import redis
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Carga variables desde backend/.env (si existe). Indicamos ruta absoluta para que
# funcione sea cual sea el cwd desde el que se lance uvicorn.
load_dotenv(Path(__file__).parent / ".env")

# Dataset GeoJSON con los aparcamientos públicos de Cáceres (Open Data).
DATA_FILE = Path(__file__).parent / "data" / "aparcamientos.geojson"

# Claves de Redis que usa la app:
#   geo:parkings   -> sorted set geoespacial con todos los aparcamientos (GEOADD / GEOSEARCH)
#   parking:{id}   -> hash con los metadatos de cada aparcamiento (HSET / HGETALL)
GEO_KEY = "geo:parkings"
PARKING_KEY_PREFIX = "parking:"

# ---------- Config (env / .env, con defaults para desarrollo) ----------
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
# CORS_ORIGINS: lista separada por comas. "*" = cualquier origen (solo dev).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]


# ---------- Modelos Pydantic ----------

class Parking(BaseModel):
    """Metadatos de un aparcamiento (corresponde al hash `parking:{id}` en Redis)."""

    id: str
    nombre: str
    clase: str
    direccion: str = ""
    nucleo: str = ""
    url: str = ""
    lat: float
    lon: float


class ParkingNearby(Parking):
    """Aparcamiento + distancia desde el punto de búsqueda (en metros)."""

    distancia_metros: float = Field(..., description="Distancia al punto consultado, en metros")


# ---------- Ciclo de vida / dependency ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Abre la conexión a Redis al arrancar la app y la cierra al apagarla."""
    # decode_responses=True -> Redis devuelve strings en lugar de bytes.
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )
    try:
        # PING: comprobación rápida de que el servidor responde. Si falla, solo logueamos;
        # los endpoints devolverán 503 cuando intenten usarlo.
        client.ping()
        logger.info("Conexión a Redis establecida en %s:%s (db=%s)", REDIS_HOST, REDIS_PORT, REDIS_DB)
    except redis.ConnectionError as exc:
        logger.warning("No se pudo conectar a Redis al arrancar: %s", exc)

    app.state.redis = client
    yield
    client.close()


app = FastAPI(
    title="AparCaceres API",
    description="API para localización de aparcamientos públicos en Cáceres usando RedisDB",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: permite que el cliente (Flutter web, navegador, etc.) llame a la API desde
# otro origen. Con "*" y allow_credentials=False funciona para dev; en producción
# conviene restringir CORS_ORIGINS a la URL real del cliente.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_redis(request: Request) -> redis.Redis:
    """Dependency de FastAPI: expone el cliente de Redis guardado en app.state."""
    return request.app.state.redis


def _raise_redis_503(exc: Exception) -> "HTTPException":
    """Helper: convierte un fallo de conexión a Redis en HTTP 503."""
    return HTTPException(status_code=503, detail=f"Redis no disponible: {exc}")


# ---------- Endpoints ----------

@app.get("/")
def read_root():
    return {"status": "Backend configurado y listo"}


@app.post("/import-parkings")
def import_parkings(rdb: redis.Redis = Depends(get_redis)):
    """Carga el dataset GeoJSON en Redis (GEOADD + HSET por feature, en pipeline)."""
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Dataset no encontrado: {DATA_FILE}",
        )

    with DATA_FILE.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    features = geojson.get("features", [])

    # Pipeline: agrupa todos los comandos y los envía en un único round-trip.
    pipe = rdb.pipeline()

    # Idempotencia: borramos datos de un import previo antes de reimportar.
    # SCAN_ITER recorre las claves `parking:*` sin bloquear Redis (al contrario que KEYS).
    try:
        old_keys = list(rdb.scan_iter(match=f"{PARKING_KEY_PREFIX}*"))
    except redis.ConnectionError as exc:
        raise _raise_redis_503(exc) from exc

    if old_keys:
        pipe.delete(*old_keys)
    pipe.delete(GEO_KEY)

    imported = 0
    for idx, feature in enumerate(features):
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        coords = geometry.get("coordinates") or []

        if len(coords) < 2:
            continue

        # GeoJSON usa [longitud, latitud].
        lon, lat = float(coords[0]), float(coords[1])
        parking_id = str(idx)

        # GEOADD: añade el miembro al sorted set geoespacial.
        pipe.geoadd(GEO_KEY, (lon, lat, parking_id))

        # HSET con mapping=dict manda un único HSET con todos los campos.
        pipe.hset(
            f"{PARKING_KEY_PREFIX}{parking_id}",
            mapping={
                "id": parking_id,
                "nombre": properties.get("NOMBRE", ""),
                "clase": properties.get("CLASE", ""),
                "direccion": properties.get("DIRECCION", ""),
                "nucleo": properties.get("NUCLEO", ""),
                "url": properties.get("URL", ""),
                "lat": lat,
                "lon": lon,
            },
        )
        imported += 1

    try:
        pipe.execute()
    except redis.ConnectionError as exc:
        raise _raise_redis_503(exc) from exc

    return {"status": "ok", "imported": imported, "geo_key": GEO_KEY}


# OJO con el orden de rutas: `/parkings/nearby` debe declararse ANTES que
# `/parkings/{parking_id}`; si no, FastAPI capturaría "nearby" como un id.

@app.get("/parkings/nearby", response_model=list[ParkingNearby])
def get_parkings_nearby(
    lat: float = Query(..., description="Latitud del punto de búsqueda"),
    lng: float = Query(..., description="Longitud del punto de búsqueda"),
    radius: float = Query(1000, ge=0, description="Radio en metros (por defecto 1000)"),
    rdb: redis.Redis = Depends(get_redis),
):
    """Devuelve los aparcamientos dentro de `radius` metros, ordenados por distancia."""
    try:
        # GEOSEARCH: búsqueda por radio sobre el índice geoespacial.
        #   - unit='m' -> distancias en metros.
        #   - withdist=True -> incluye la distancia en el resultado.
        #   - sort='ASC' -> ordena del más cercano al más lejano (lo hace Redis).
        # Formato devuelto con withdist=True: [[member, distance], ...].
        results = rdb.geosearch(
            GEO_KEY,
            longitude=lng,
            latitude=lat,
            radius=radius,
            unit="m",
            withdist=True,
            sort="ASC",
        )
    except redis.ConnectionError as exc:
        raise _raise_redis_503(exc) from exc

    if not results:
        return []

    # Separamos ids y distancias preservando el orden de Redis.
    ids = [row[0] for row in results]
    distances = [float(row[1]) for row in results]

    # Pipeline para recuperar todos los hashes en un único round-trip.
    pipe = rdb.pipeline()
    for parking_id in ids:
        pipe.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")
    try:
        hashes = pipe.execute()
    except redis.ConnectionError as exc:
        raise _raise_redis_503(exc) from exc

    out: list[ParkingNearby] = []
    for parking_id, dist, data in zip(ids, distances, hashes):
        if not data:
            # Miembro presente en geo:parkings pero sin hash asociado -> lo saltamos.
            logger.warning("parking:%s está en geo pero no tiene hash", parking_id)
            continue
        out.append(ParkingNearby(**data, distancia_metros=dist))

    return out


@app.get("/parkings/{parking_id}", response_model=Parking)
def get_parking(parking_id: str, rdb: redis.Redis = Depends(get_redis)):
    """Devuelve el detalle de un aparcamiento leyendo su hash `parking:{id}`."""
    try:
        # HGETALL: devuelve todos los campos del hash como dict (vacío si no existe).
        data = rdb.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")
    except redis.ConnectionError as exc:
        raise _raise_redis_503(exc) from exc

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Aparcamiento {parking_id!r} no encontrado",
        )

    return Parking(**data)
