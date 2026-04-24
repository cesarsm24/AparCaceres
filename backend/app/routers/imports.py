import json
import logging

import redis
from fastapi import APIRouter, Depends, HTTPException

from ..config import CACHE_NEARBY_PREFIX, DATA_FILE, GEO_KEY, PARKING_KEY_PREFIX
from ..redis_client import get_redis, raise_redis_503

logger = logging.getLogger(__name__)

router = APIRouter(tags=["imports"])


@router.post("/import-parkings")
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
        raise raise_redis_503(exc) from exc

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
        raise raise_redis_503(exc) from exc

    # Invalidación de caché: al reimportar, los resultados anteriores de /parkings/nearby
    # dejan de ser válidos. Borramos todas las claves cache:nearby:*.
    try:
        cache_keys = list(rdb.scan_iter(match=f"{CACHE_NEARBY_PREFIX}*"))
        if cache_keys:
            rdb.delete(*cache_keys)
    except redis.ConnectionError:
        # No bloqueamos el import si la invalidación falla; el TTL se encargará.
        logger.warning("No se pudo invalidar cache:nearby:* al reimportar")
        cache_keys = []

    return {
        "status": "ok",
        "imported": imported,
        "geo_key": GEO_KEY,
        "cache_invalidated": len(cache_keys),
    }
