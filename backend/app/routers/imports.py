import logging

import redis
from fastapi import APIRouter, Depends

from ..config import DATA_DIR
from ..importer import run_import_dir
from ..redis_client import get_redis, raise_redis_503

logger = logging.getLogger(__name__)

router = APIRouter(tags=["imports"])


# Ejemplo OpenAPI: refleja la respuesta multi-fichero (totales + desglose).
_IMPORT_RESPONSE_EXAMPLE = {
    "status": "ok",
    "imported": 22934,
    "skipped": 12,
    "geo_key": "geo:parkings",
    "cache_invalidated": 3,
    "files_processed": 11,
    "files_skipped": [],
    "sources": [
        {"sourceDataset": "aparcamientos", "imported": 24, "skipped": 0},
        {"sourceDataset": "aparcamientos_en_bateria", "imported": 1424, "skipped": 0},
        {"sourceDataset": "aparcamientos_en_linea", "imported": 4779, "skipped": 0},
        {"sourceDataset": "carga_descarga", "imported": 73, "skipped": 0},
        {"sourceDataset": "movilidad_reducida", "imported": 743, "skipped": 0},
        {"sourceDataset": "parking_bicis", "imported": 68, "skipped": 0},
        {"sourceDataset": "parking_motos_areas", "imported": 48, "skipped": 0},
        {"sourceDataset": "parking_motos_puntos", "imported": 46, "skipped": 0},
        {"sourceDataset": "parkings", "imported": 8, "skipped": 0},
        {"sourceDataset": "parkings_en_superficie", "imported": 15620, "skipped": 12},
        {"sourceDataset": "zona_azul", "imported": 101, "skipped": 0},
    ],
}


@router.post(
    "/import-parkings",
    summary="Reimporta todos los GeoJSON del directorio de datos",
    description=(
        "Procesa por lotes todos los `*.geojson` de `backend/data/`, "
        "normalizando cada feature contra el contrato móvil "
        "(`ParkingPlaceOut`).\n\n"
        "El importador infiere `category`/`vehicleType`/`regulation` a partir "
        "del nombre del fichero cuando el feature no los aporta (p. ej. "
        "`zona_azul.geojson` -> `blue_zone`/`car`/`blue_zone`), y genera ids "
        "deterministas con un fallback hash basado en filename + coordenadas "
        "cuando no hay `mslink` ni `id` explícito.\n\n"
        "Idempotente: limpia `parking:*` y `geo:parkings` antes de reescribir, "
        "e invalida la caché `cache:nearby:*`. La respuesta incluye totales y "
        "desglose por `sourceDataset`."
    ),
    responses={
        200: {
            "content": {"application/json": {"example": _IMPORT_RESPONSE_EXAMPLE}}
        }
    },
)
def import_parkings(rdb: redis.Redis = Depends(get_redis)):
    try:
        return run_import_dir(DATA_DIR, rdb)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
