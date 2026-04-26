"""Endpoints de lectura del catálogo de aparcamientos.

Los listados usan Redis Stack / RediSearch como índice principal. El hash
`parking:{id}` sigue siendo la fuente canónica del contrato Flutter.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import redis
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..config import (
    CACHE_NEARBY_PREFIX,
    CACHE_NEARBY_TTL,
    CACHE_VERSION_KEY,
    DEFAULT_PARKING_LIMIT,
    MAX_PARKING_LIMIT,
    PARKING_KEY_PREFIX,
    SEARCH_INDEX_NAME,
)
from ..enums import ParkingCategory, ParkingRegulation, ParkingVehicleType
from ..importer import place_from_redis_hash
from ..rate_limit import RATE_LIMIT_NEARBY, limiter
from ..redis_client import get_redis, get_redis_sync, raise_redis_503
from ..schemas import (
    ParkingFacetsOut,
    ParkingPlaceOut,
    ParkingPlacesEnvelopeOut,
    ParkingPlacesNearbyEnvelopeOut,
)
from ..search import (
    SearchIndexError,
    get_facets,
    search_in_bounds,
    search_nearby,
    search_parkings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parkings", tags=["parkings"])


def _resolve_limit(value: Optional[int]) -> int:
    if value is None or value <= 0:
        return DEFAULT_PARKING_LIMIT
    return min(value, MAX_PARKING_LIMIT)


def _resolve_offset(value: int) -> int:
    return max(0, value)


def _set_pagination_headers(
    response: Response,
    *,
    total: int,
    limit: int,
    offset: int,
) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Truncated"] = "true" if offset + limit < total else "false"
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)


def _to_envelope(
    *,
    items: list[ParkingPlaceOut],
    total: int,
    limit: int,
    offset: int,
    facets: Optional[ParkingFacetsOut] = None,
) -> ParkingPlacesEnvelopeOut:
    return ParkingPlacesEnvelopeOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total,
        facets=facets,
    )


def _to_nearby_envelope(
    *,
    items,
    total: int,
    limit: int,
    offset: int,
) -> ParkingPlacesNearbyEnvelopeOut:
    return ParkingPlacesNearbyEnvelopeOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total,
        facets=None,
    )


def _search_error(exc: SearchIndexError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


_PLACE_POINT_EXAMPLE = {
    "id": "aparcamientos:1903",
    "name": "Escuela Politecnica",
    "category": "parking",
    "vehicleType": "car",
    "regulation": "free",
    "geometryType": "point",
    "latitude": 39.4784863854682,
    "longitude": -6.34204232071547,
    "coordinates": None,
    "totalSpaces": None,
    "streetName": None,
    "streetType": None,
    "district": "CÁCERES",
    "neighborhood": None,
    "sourceDataset": "aparcamientos",
    "imageUrl": None,
    "urlFicha": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903",
    "urlVia": None,
    "management": None,
}

_PLACE_POLYGON_EXAMPLE = {
    "id": "aparcamientos_en_linea:5500",
    "name": "Calle Dalia",
    "category": "street_line",
    "vehicleType": "car",
    "regulation": "free",
    "geometryType": "polygon",
    "latitude": 39.466668,
    "longitude": -6.399310,
    "coordinates": [
        [
            [-6.3994515, 39.4670139],
            [-6.3991710, 39.4663191],
            [-6.3991416, 39.4663258],
            [-6.3994238, 39.4670207],
            [-6.3994515, 39.4670139],
        ]
    ],
    "totalSpaces": 16,
    "streetName": "DALIA",
    "streetType": "CALLE",
    "district": "OESTE",
    "neighborhood": "EL JUNQUILLO",
    "sourceDataset": "aparcamientos_en_linea",
    "imageUrl": None,
    "urlFicha": None,
    "urlVia": None,
    "management": None,
}

_PLACE_NEARBY_EXAMPLE = {**_PLACE_POINT_EXAMPLE, "distanceMeters": 124.7}

_LIST_ENVELOPE_EXAMPLE = {
    "items": [_PLACE_POINT_EXAMPLE, _PLACE_POLYGON_EXAMPLE],
    "total": 2,
    "limit": DEFAULT_PARKING_LIMIT,
    "offset": 0,
    "truncated": False,
    "facets": None,
}

_NEARBY_ENVELOPE_EXAMPLE = {
    "items": [_PLACE_NEARBY_EXAMPLE],
    "total": 1,
    "limit": DEFAULT_PARKING_LIMIT,
    "offset": 0,
    "truncated": False,
    "facets": None,
}

_CATEGORIES_EXAMPLE = ["parking", "paid_parking", "street_line", "blue_zone"]

_FACETS_EXAMPLE = {
    "total": 7314,
    "categories": {
        "parking": 24,
        "paid_parking": 8,
        "street_line": 4779,
        "street_battery": 1424,
        "blue_zone": 101,
        "accessible": 743,
        "motorbike": 94,
        "bicycle": 68,
        "loading": 73,
    },
    "vehicleTypes": {"car": 7152, "motorbike": 94, "bike": 68},
    "regulations": {
        "free": 6227,
        "paid": 8,
        "blue_zone": 101,
        "loading": 73,
        "reserved": 905,
    },
    "datasets": {
        "aparcamientos": 24,
        "aparcamientos_en_bateria": 1424,
        "aparcamientos_en_linea": 4779,
        "carga_descarga": 73,
        "movilidad_reducida": 743,
        "parking_bicis": 68,
        "parking_motos_areas": 48,
        "parking_motos_puntos": 46,
        "parkings": 8,
        "zona_azul": 101,
    },
}


@router.get(
    "",
    response_model=ParkingPlacesEnvelopeOut,
    summary="Lista aparcamientos con filtros opcionales",
    description=(
        "Devuelve un envelope paginado `{items,total,limit,offset,truncated,facets}`. "
        f"Las consultas se resuelven con RediSearch (`{SEARCH_INDEX_NAME}`) sobre "
        "los hashes `parking:{id}`. OR dentro de cada filtro repetible y AND "
        "entre dimensiones distintas."
    ),
    responses={200: {"content": {"application/json": {"example": _LIST_ENVELOPE_EXAMPLE}}}},
)
async def list_parkings(
    response: Response,
    ids: Optional[list[str]] = Query(None, description="Filtra por id, repetible."),
    q: Optional[str] = Query(None, description="Búsqueda libre accent-insensitive."),
    vehicleType: Optional[list[ParkingVehicleType]] = Query(None),
    category: Optional[list[ParkingCategory]] = Query(None),
    regulation: Optional[list[ParkingRegulation]] = Query(None),
    dataset: Optional[list[str]] = Query(None, description="Dataset de origen, repetible."),
    minSpaces: int = Query(0, ge=0),
    offset: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=0),
    includeFacets: bool = Query(False, description="Incluye facets globales del catálogo."),
    rdb_sync: redis.Redis = Depends(get_redis_sync),
):
    effective_limit = _resolve_limit(limit)
    effective_offset = _resolve_offset(offset)
    try:
        # Las funciones de `app/search.py` son síncronas (parsing/build de
        # queries pesado, llamadas a Redis bloqueantes). Las lanzamos en el
        # threadpool para no bloquear el event loop.
        result = await asyncio.to_thread(
            search_parkings,
            rdb_sync,
            ids=ids,
            q=q,
            vehicle_types=vehicleType,
            categories=category,
            regulations=regulation,
            datasets=dataset,
            min_spaces=minSpaces,
            offset=effective_offset,
            limit=effective_limit,
        )
        facets = (
            await asyncio.to_thread(get_facets, rdb_sync)
            if includeFacets
            else None
        )
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    except SearchIndexError as exc:
        raise _search_error(exc) from exc

    _set_pagination_headers(
        response,
        total=result.total,
        limit=effective_limit,
        offset=effective_offset,
    )
    return _to_envelope(
        items=result.items,
        total=result.total,
        limit=effective_limit,
        offset=effective_offset,
        facets=facets,
    )


@router.get(
    "/nearby",
    response_model=ParkingPlacesNearbyEnvelopeOut,
    summary="Aparcamientos dentro de un radio, ordenados por distancia",
    description=(
        "Busca por `@location:[lng lat radio m]` en RediSearch y devuelve un "
        "envelope paginado. `radius` se mantiene como alias legacy de "
        "`radiusMeters`."
    ),
    responses={200: {"content": {"application/json": {"example": _NEARBY_ENVELOPE_EXAMPLE}}}},
)
@limiter.limit(RATE_LIMIT_NEARBY)
async def get_parkings_nearby(
    request: Request,
    response: Response,
    lat: float = Query(..., description="Latitud del centro de búsqueda."),
    lng: float = Query(..., description="Longitud del centro de búsqueda."),
    radiusMeters: Optional[float] = Query(None, ge=0, description="Radio en metros."),
    radius: Optional[float] = Query(None, ge=0, deprecated=True),
    ids: Optional[list[str]] = Query(None),
    q: Optional[str] = Query(None),
    vehicleType: Optional[list[ParkingVehicleType]] = Query(None),
    category: Optional[list[ParkingCategory]] = Query(None),
    regulation: Optional[list[ParkingRegulation]] = Query(None),
    dataset: Optional[list[str]] = Query(None),
    minSpaces: int = Query(0, ge=0),
    offset: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=0),
    rdb: aioredis.Redis = Depends(get_redis),
    rdb_sync: redis.Redis = Depends(get_redis_sync),
):
    effective_radius = radiusMeters if radiusMeters is not None else (radius or 1000.0)
    effective_limit = _resolve_limit(limit)
    effective_offset = _resolve_offset(offset)

    has_filters = bool(
        ids
        or q
        or vehicleType
        or category
        or regulation
        or dataset
        or minSpaces > 0
        or limit is not None
        or effective_offset > 0
    )
    cache_enabled = CACHE_NEARBY_TTL > 0 and not has_filters
    cache_key: Optional[str] = None

    if cache_enabled:
        # Versión global namespaceada en la clave: al reimportar incrementamos
        # `cache:version` y todas las claves antiguas quedan inalcanzables sin
        # tener que hacer SCAN+DEL. Las huérfanas las recoge el TTL.
        try:
            version = await rdb.get(CACHE_VERSION_KEY) or "0"
        except redis.ConnectionError:
            version = "0"
        cache_key = (
            f"{CACHE_NEARBY_PREFIX}v{version}:"
            f"{lat:.4f}:{lng:.4f}:{int(effective_radius)}"
        )
        try:
            cached = await rdb.get(cache_key)
        except redis.ConnectionError:
            cached = None
        if cached is not None:
            return Response(
                content=cached,
                media_type="application/json",
                headers={"X-Cache": "HIT"},
            )

    try:
        result = await asyncio.to_thread(
            search_nearby,
            rdb_sync,
            lat=lat,
            lng=lng,
            radius_meters=effective_radius,
            ids=ids,
            q=q,
            vehicle_types=vehicleType,
            categories=category,
            regulations=regulation,
            datasets=dataset,
            min_spaces=minSpaces,
            offset=effective_offset,
            limit=effective_limit,
        )
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    except SearchIndexError as exc:
        raise _search_error(exc) from exc

    envelope = _to_nearby_envelope(
        items=result.items,
        total=result.total,
        limit=effective_limit,
        offset=effective_offset,
    )
    if cache_enabled and cache_key is not None:
        try:
            await rdb.setex(cache_key, CACHE_NEARBY_TTL, envelope.model_dump_json())
        except redis.ConnectionError:
            logger.warning("No se pudo escribir caché %s", cache_key)

    response.headers["X-Cache"] = "MISS" if cache_enabled else "BYPASS"
    _set_pagination_headers(
        response,
        total=result.total,
        limit=effective_limit,
        offset=effective_offset,
    )
    return envelope


@router.get(
    "/in-bounds",
    response_model=ParkingPlacesEnvelopeOut,
    summary="Aparcamientos dentro de un viewport rectangular",
    description=(
        "Filtra por rango numérico indexado de `latitude` y `longitude`, pensado "
        "para cargar solo lo visible en el mapa."
    ),
    responses={
        200: {"content": {"application/json": {"example": _LIST_ENVELOPE_EXAMPLE}}},
        400: {"description": "Bounding box inválido."},
    },
)
async def get_parkings_in_bounds(
    response: Response,
    minLat: float = Query(...),
    minLng: float = Query(...),
    maxLat: float = Query(...),
    maxLng: float = Query(...),
    vehicleType: Optional[list[ParkingVehicleType]] = Query(None),
    category: Optional[list[ParkingCategory]] = Query(None),
    regulation: Optional[list[ParkingRegulation]] = Query(None),
    dataset: Optional[list[str]] = Query(None),
    minSpaces: int = Query(0, ge=0),
    offset: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=0),
    rdb_sync: redis.Redis = Depends(get_redis_sync),
):
    if minLat >= maxLat or minLng >= maxLng:
        raise HTTPException(
            status_code=400,
            detail="bounds inválidos: minLat<maxLat y minLng<maxLng requerido",
        )

    effective_limit = _resolve_limit(limit)
    effective_offset = _resolve_offset(offset)
    try:
        result = await asyncio.to_thread(
            search_in_bounds,
            rdb_sync,
            min_lat=minLat,
            min_lng=minLng,
            max_lat=maxLat,
            max_lng=maxLng,
            vehicle_types=vehicleType,
            categories=category,
            regulations=regulation,
            datasets=dataset,
            min_spaces=minSpaces,
            offset=effective_offset,
            limit=effective_limit,
        )
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    except SearchIndexError as exc:
        raise _search_error(exc) from exc

    _set_pagination_headers(
        response,
        total=result.total,
        limit=effective_limit,
        offset=effective_offset,
    )
    return _to_envelope(
        items=result.items,
        total=result.total,
        limit=effective_limit,
        offset=effective_offset,
    )


@router.get(
    "/categories",
    response_model=list[ParkingCategory],
    summary="Categorías presentes en el catálogo",
    responses={200: {"content": {"application/json": {"example": _CATEGORIES_EXAMPLE}}}},
)
async def list_categories(rdb_sync: redis.Redis = Depends(get_redis_sync)):
    try:
        facets = await asyncio.to_thread(get_facets, rdb_sync)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    except SearchIndexError as exc:
        raise _search_error(exc) from exc
    return [cat for cat in ParkingCategory if facets.categories.get(cat.value, 0) > 0]


@router.get(
    "/facets",
    response_model=ParkingFacetsOut,
    summary="Conteos del catálogo por categoría / vehículo / régimen / dataset",
    responses={200: {"content": {"application/json": {"example": _FACETS_EXAMPLE}}}},
)
async def list_facets(rdb_sync: redis.Redis = Depends(get_redis_sync)):
    try:
        return await asyncio.to_thread(get_facets, rdb_sync)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    except SearchIndexError as exc:
        raise _search_error(exc) from exc


@router.get(
    "/{parking_id}",
    response_model=ParkingPlaceOut,
    summary="Detalle de un aparcamiento",
    description="Devuelve un único `ParkingPlace` por id. 404 si no existe.",
    responses={
        200: {"content": {"application/json": {"example": _PLACE_POLYGON_EXAMPLE}}},
        404: {"description": "El aparcamiento no existe en Redis."},
    },
)
async def get_parking(
    parking_id: str,
    rdb: aioredis.Redis = Depends(get_redis),
):
    try:
        data = await rdb.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Aparcamiento {parking_id!r} no encontrado",
        )

    return place_from_redis_hash(data)
