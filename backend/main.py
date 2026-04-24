import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis
from fastapi import Depends, FastAPI, HTTPException, Request

logger = logging.getLogger(__name__)

# Dataset GeoJSON con los aparcamientos públicos de Cáceres (Open Data).
DATA_FILE = Path(__file__).parent / "data" / "aparcamientos.geojson"

# Claves de Redis que usa la app:
#   geo:parkings   -> sorted set geoespacial con todos los aparcamientos (comando GEOADD)
#   parking:{id}   -> hash con los metadatos de cada aparcamiento (comando HSET)
GEO_KEY = "geo:parkings"
PARKING_KEY_PREFIX = "parking:"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Abre la conexión a Redis al arrancar la app y la cierra al apagarla.

    Usamos el patrón `lifespan` (sustituye a on_event) para que el cliente viva
    durante toda la vida del proceso y se reutilice entre requests.
    """
    # decode_responses=True hace que Redis devuelva strings en lugar de bytes,
    # más cómodo para serializar a JSON con FastAPI.
    client = redis.Redis(
        host="localhost",
        port=6379,
        db=0,
        decode_responses=True,
    )
    try:
        # PING: comprobación rápida de que el servidor responde. Si Redis no está
        # levantado, lo avisamos por log pero dejamos que la app arranque igual
        # (los endpoints fallarán con 503 cuando intenten usarlo).
        client.ping()
        logger.info("Conexión a Redis establecida en localhost:6379")
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


def get_redis(request: Request) -> redis.Redis:
    """Dependency de FastAPI: expone el cliente de Redis guardado en app.state."""
    return request.app.state.redis


@app.get("/")
def read_root():
    return {"status": "Backend configurado y listo"}


@app.post("/import-parkings")
def import_parkings(r: redis.Redis = Depends(get_redis)):
    """Carga el dataset GeoJSON en Redis.

    - Crea un índice geoespacial en `geo:parkings` (GEOADD).
    - Guarda los metadatos de cada aparcamiento en un hash `parking:{id}` (HSET).
    - Todo se manda en un pipeline para reducir round-trips a Redis.
    """
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Dataset no encontrado: {DATA_FILE}",
        )

    with DATA_FILE.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    features = geojson.get("features", [])

    # El pipeline agrupa comandos y los envía en un único round-trip al ejecutar.
    # Para N features pasamos de ~2N round-trips (GEOADD + HSET por cada uno) a 1.
    pipe = r.pipeline()

    # Idempotencia: borramos los datos del import anterior antes de reimportar.
    # SCAN_ITER recorre las claves `parking:*` sin bloquear Redis (a diferencia de KEYS).
    old_keys = list(r.scan_iter(match=f"{PARKING_KEY_PREFIX}*"))
    if old_keys:
        # DEL borra todas las claves pasadas como argumentos en una sola operación.
        pipe.delete(*old_keys)
    # También limpiamos el índice geo para que no queden miembros huérfanos.
    pipe.delete(GEO_KEY)

    imported = 0
    for idx, feature in enumerate(features):
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        coords = geometry.get("coordinates") or []

        if len(coords) < 2:
            # Feature sin geometría válida -> lo saltamos sin romper el import.
            continue

        # Ojo al orden: GeoJSON almacena [longitud, latitud].
        lon, lat = float(coords[0]), float(coords[1])

        # No hay un ID explícito en properties -> usamos el índice como identificador.
        parking_id = str(idx)

        # GEOADD añade un miembro al sorted set geoespacial `geo:parkings`.
        # Internamente Redis codifica (lon, lat) como un geohash y lo usa como score,
        # lo que permite luego consultas GEOSEARCH / GEORADIUS por proximidad.
        # Firma en redis-py: geoadd(name, values) donde values = (lon, lat, member, ...).
        pipe.geoadd(GEO_KEY, (lon, lat, parking_id))

        # HSET guarda los metadatos en un hash (estructura campo -> valor, tipo "fila").
        # Pasando mapping=dict, redis-py manda un único HSET con todos los campos,
        # en lugar de un HSET por campo.
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

    # EXECUTE vacía la cola del pipeline y manda todos los comandos a Redis.
    # Si Redis no está disponible, lanza redis.ConnectionError aquí.
    try:
        pipe.execute()
    except redis.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Redis no disponible: {exc}",
        ) from exc

    return {
        "status": "ok",
        "imported": imported,
        "geo_key": GEO_KEY,
    }
