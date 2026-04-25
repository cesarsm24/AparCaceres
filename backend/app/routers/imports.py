import json
import logging

import redis
from fastapi import APIRouter, Depends, HTTPException

from ..config import DATA_FILE
from ..importer import run_import
from ..redis_client import get_redis, raise_redis_503

logger = logging.getLogger(__name__)

router = APIRouter(tags=["imports"])


@router.post("/import-parkings")
def import_parkings(rdb: redis.Redis = Depends(get_redis)):
    """Carga el dataset GeoJSON en Redis siguiendo el contrato móvil.

    Lee el fichero, delega el ciclo completo (limpieza idempotente + GEOADD/HSET
    + invalidación de caché) en `app.importer.run_import` y traduce fallos de
    conexión a Redis a HTTP 503.
    """
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Dataset no encontrado: {DATA_FILE}",
        )

    with DATA_FILE.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    features = geojson.get("features", [])

    try:
        return run_import(features, rdb)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
