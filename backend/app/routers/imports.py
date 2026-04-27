"""Endpoint de reimportación del catálogo desde los GeoJSON locales.

Protección con `X-Import-Token`:
- Si la variable de entorno `IMPORT_TOKEN` está definida, el endpoint exige
  que la petición incluya esa cabecera y que coincida (constant-time compare)
  con el valor configurado. En caso contrario responde 401.
- Si `IMPORT_TOKEN` está vacío (default en dev), el endpoint queda abierto
  para que sea cómodo iterar localmente.
"""

import asyncio
import hmac
import logging
from typing import Optional

import redis
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..config import DATA_DIR, IMPORT_TOKEN
from ..importer import run_import_dir
from ..rate_limit import RATE_LIMIT_IMPORT, limiter
from ..redis_client import get_redis_sync, raise_redis_503
from ..search import SearchIndexError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["imports"])


# Ejemplo OpenAPI: refleja la respuesta multi-fichero (totales + desglose).
_IMPORT_RESPONSE_EXAMPLE = {
    "status": "ok",
    "imported": 7314,
    "skipped": 0,
    "search_index": "idx:parkings_search",
    "ids_disambiguated": 11,
    "cache_version": 7,
    "files_processed": 10,
    "files_skipped": [],
    "excluded_datasets": ["parkings_en_superficie.geojson"],
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
        {"sourceDataset": "zona_azul", "imported": 101, "skipped": 0},
    ],
}


def _check_import_token(provided: Optional[str]) -> None:
    """Valida `X-Import-Token`; lanza 401 si está mal o falta cuando hace falta.

    Comparación con `hmac.compare_digest` para evitar timing attacks (overkill
    en este contexto pero es el patrón correcto y cuesta lo mismo).
    """
    if not IMPORT_TOKEN:
        # Sin token configurado, dev abierto.
        return
    expected = IMPORT_TOKEN
    given = (provided or "").strip()
    if not given:
        raise HTTPException(
            status_code=401,
            detail="Falta cabecera X-Import-Token",
        )
    if not hmac.compare_digest(given, expected):
        raise HTTPException(
            status_code=401,
            detail="X-Import-Token inválido",
        )


@router.post(
    "/import-parkings",
    summary="Reimporta todos los GeoJSON activos del directorio de datos",
    description=(
        "Procesa por lotes los `*.geojson` activos de `backend/data/`, "
        "normalizando cada feature contra el contrato móvil "
        "(`ParkingPlaceOut`). El fichero `parkings_en_superficie.geojson` se "
        "ignora aunque esté presente físicamente.\n\n"
        "El importador infiere `category`/`vehicleType`/`regulation` a partir "
        "del nombre del fichero cuando el feature no los aporta (p. ej. "
        "`zona_azul.geojson` -> `blue_zone`/`car`/`blue_zone`), genera ids "
        "namespaced por dataset (`{sourceDataset}:{key}`) y recrea el índice "
        "Redis Stack / RediSearch `idx:parkings_search` sobre los hashes "
        "`parking:{id}`.\n\n"
        "Idempotente: construye la nueva generación bajo `parking_v2:*` y "
        "hace el swap al catálogo activo (`UNLINK` del viejo + `RENAME` del "
        "staging). Invalida la caché de `/parkings/nearby` incrementando "
        "`cache:version` (O(1), sin SCAN). "
        "La respuesta incluye totales, desglose por `sourceDataset` y el nuevo "
        "`cache_version`.\n\n"
        "Si `IMPORT_TOKEN` está configurado en el entorno, la petición debe "
        "incluir la cabecera `X-Import-Token` con ese valor (401 si no)."
    ),
    responses={
        200: {
            "content": {"application/json": {"example": _IMPORT_RESPONSE_EXAMPLE}}
        },
        401: {"description": "Falta o no coincide `X-Import-Token`."},
    },
)
@limiter.limit(RATE_LIMIT_IMPORT)
async def import_parkings(
    request: Request,
    x_import_token: Optional[str] = Header(
        None,
        alias="X-Import-Token",
        description="Token de autorización. Obligatorio si `IMPORT_TOKEN` está configurado.",
    ),
    rdb_sync: redis.Redis = Depends(get_redis_sync),
):
    _check_import_token(x_import_token)
    try:
        # `run_import_dir` lee del disco, parsea GeoJSON y mete miles de
        # HSET en pipeline: completamente síncrono. Lo lanzamos en el
        # threadpool para no congelar el event loop durante el import.
        return await asyncio.to_thread(run_import_dir, DATA_DIR, rdb_sync)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    except SearchIndexError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
