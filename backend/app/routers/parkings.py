"""Endpoints de lectura del catálogo de aparcamientos.

Forman el contrato HTTP que consume el cliente Flutter (`ParkingPlace.fromJson`).
Las respuestas usan los schemas del contrato móvil (`ParkingPlaceOut`,
`ParkingPlaceNearbyOut`) y las query params replican los filtros del
`ParkingQuery` y de `searchParking` del cliente.

Reglas de routing:
- `/parkings/nearby` y `/parkings/categories` se declaran ANTES que
  `/parkings/{parking_id}` para que el path param no los capture.

Cache:
- `/parkings/nearby` aplica look-aside SOLO cuando no llegan filtros: con
  filtros la cardinalidad de la clave explotaría y la caché perdería sentido.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..config import (
    CACHE_NEARBY_PREFIX,
    CACHE_NEARBY_TTL,
    GEO_KEY,
    PARKING_KEY_PREFIX,
)
from ..enums import ParkingCategory, ParkingRegulation, ParkingVehicleType
from ..filters import apply_filters, normalize_for_search
from ..importer import place_from_redis_hash
from ..redis_client import get_redis, raise_redis_503
from ..schemas import ParkingPlaceNearbyOut, ParkingPlaceOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parkings", tags=["parkings"])


# ============================================================
# Helpers internos
# ============================================================

def _scan_all_ids(rdb: redis.Redis) -> list[str]:
    """Lista los ids de aparcamiento presentes en Redis (sin el prefijo)."""
    prefix_len = len(PARKING_KEY_PREFIX)
    return [k[prefix_len:] for k in rdb.scan_iter(match=f"{PARKING_KEY_PREFIX}*")]


def _load_places(rdb: redis.Redis, parking_ids: list[str]) -> list[ParkingPlaceOut]:
    """Pipeline de `HGETALL` -> lista de `ParkingPlaceOut`.

    Mantiene el orden de `parking_ids`. Salta silenciosamente los ids cuyo
    hash no exista (caso degradado: id en el índice geo pero borrado del hash).
    """
    if not parking_ids:
        return []
    pipe = rdb.pipeline()
    for pid in parking_ids:
        pipe.hgetall(f"{PARKING_KEY_PREFIX}{pid}")
    hashes = pipe.execute()

    out: list[ParkingPlaceOut] = []
    for pid, data in zip(parking_ids, hashes):
        if not data:
            logger.warning("parking:%s sin hash; ignorando", pid)
            continue
        out.append(place_from_redis_hash(data))
    return out


# ============================================================
# Ejemplos OpenAPI compartidos
# ============================================================

_PLACE_POINT_EXAMPLE = {
    "id": "aparcamiento-1903",
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
    "sourceDataset": None,
    "imageUrl": None,
    "urlFicha": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903",
    "urlVia": None,
    "management": None,
}

_PLACE_POLYGON_EXAMPLE = {
    "id": "aparcamiento-5500",
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

_CATEGORIES_EXAMPLE = ["parking", "paid_parking", "street_line", "blue_zone"]


# ============================================================
# GET /parkings — listado completo con filtros opcionales
# ============================================================

@router.get(
    "",
    response_model=list[ParkingPlaceOut],
    summary="Lista aparcamientos con filtros opcionales",
    description=(
        "Devuelve todos los aparcamientos del catálogo, con el shape de "
        "`ParkingPlace.fromJson`. Sin paginación obligatoria.\n\n"
        "Si se pasan `ids`, solo se cargan esas claves (uso típico: pantalla "
        "de favoritos). Los filtros restantes (`q`, `vehicleType`, `category`, "
        "`regulation`, `minSpaces`) se aplican como AND.\n\n"
        "`q` es accent-insensitive y busca en `name`, `streetName`, "
        "`streetType`, `district` y `neighborhood` (mismo subset que el "
        "buscador del cliente Flutter)."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [_PLACE_POINT_EXAMPLE, _PLACE_POLYGON_EXAMPLE]
                }
            }
        }
    },
)
def list_parkings(
    ids: Optional[list[str]] = Query(
        None,
        description="Filtra por id (repetible). Si se pasa, los demás filtros operan sobre ese subconjunto.",
    ),
    q: Optional[str] = Query(
        None,
        description="Búsqueda libre (accent-insensitive) sobre name/streetName/streetType/district/neighborhood.",
        examples=["dalia", "polit", "centro"],
    ),
    vehicleType: Optional[list[ParkingVehicleType]] = Query(
        None,
        description="Filtra por tipo de vehículo (repetible). OR dentro del param.",
    ),
    category: Optional[list[ParkingCategory]] = Query(
        None,
        description="Filtra por categoría (repetible). OR dentro del param.",
    ),
    regulation: Optional[list[ParkingRegulation]] = Query(
        None,
        description="Filtra por régimen (repetible). OR dentro del param.",
    ),
    minSpaces: int = Query(
        0,
        ge=0,
        description="Plazas mínimas. Aparcamientos sin `totalSpaces` se descartan si > 0.",
    ),
    rdb: redis.Redis = Depends(get_redis),
):
    try:
        # Optimización: si vienen ids explícitos, cargamos solo esos en lugar
        # de escanear todo el catálogo y filtrar después.
        target_ids = ids if ids else _scan_all_ids(rdb)
        places = _load_places(rdb, target_ids)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    return apply_filters(
        places,
        # `ids` ya restringió la carga; no hace falta refiltrar.
        ids=None,
        normalized_q=normalize_for_search(q) if q else None,
        vehicle_types=set(vehicleType) if vehicleType else None,
        categories=set(category) if category else None,
        regulations=set(regulation) if regulation else None,
        min_spaces=minSpaces,
    )


# ============================================================
# GET /parkings/nearby — búsqueda por proximidad con GEOSEARCH
# ============================================================

@router.get(
    "/nearby",
    response_model=list[ParkingPlaceNearbyOut],
    summary="Aparcamientos dentro de un radio, ordenados por distancia",
    description=(
        "Resuelve por `GEOSEARCH` sobre `geo:parkings` (centroide del polígono "
        "/ punto medio de la línea para no-points) y luego aplica los mismos "
        "filtros que `GET /parkings`.\n\n"
        "El campo extra `distanceMeters` viene en metros y NO forma parte del "
        "contrato `ParkingPlace.fromJson` — el cliente puede ignorarlo.\n\n"
        "`radius` se admite como alias legacy de `radiusMeters` (deprecado). "
        "Si llegan ambos, `radiusMeters` gana.\n\n"
        "La caché look-aside (`cache:nearby:*`, header `X-Cache: HIT|MISS|BYPASS`) "
        "solo se usa cuando no se aplican filtros, para no inflar el espacio "
        "de claves."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"example": [_PLACE_NEARBY_EXAMPLE]}
            }
        }
    },
)
def get_parkings_nearby(
    response: Response,
    lat: float = Query(..., description="Latitud del centro de búsqueda."),
    lng: float = Query(..., description="Longitud del centro de búsqueda."),
    radiusMeters: Optional[float] = Query(
        None,
        ge=0,
        description="Radio en metros. Default 1000. Alias preferido frente a `radius`.",
    ),
    radius: Optional[float] = Query(
        None,
        ge=0,
        deprecated=True,
        description="Alias legacy de `radiusMeters`. Mantener solo por compatibilidad.",
    ),
    ids: Optional[list[str]] = Query(None, description="Restringe a este subconjunto de ids."),
    q: Optional[str] = Query(None, description="Búsqueda accent-insensitive (mismos campos que `/parkings`)."),
    vehicleType: Optional[list[ParkingVehicleType]] = Query(None),
    category: Optional[list[ParkingCategory]] = Query(None),
    regulation: Optional[list[ParkingRegulation]] = Query(None),
    minSpaces: int = Query(0, ge=0),
    rdb: redis.Redis = Depends(get_redis),
):
    # Resolución de radio: explícito > legacy > default.
    if radiusMeters is not None:
        effective_radius = radiusMeters
    elif radius is not None:
        effective_radius = radius
    else:
        effective_radius = 1000.0

    has_filters = bool(
        ids or q or vehicleType or category or regulation or minSpaces > 0
    )
    cache_enabled = CACHE_NEARBY_TTL > 0 and not has_filters
    cache_key = f"{CACHE_NEARBY_PREFIX}{lat:.4f}:{lng:.4f}:{int(effective_radius)}"

    if cache_enabled:
        try:
            cached = rdb.get(cache_key)
        except redis.ConnectionError:
            cached = None
        if cached is not None:
            return Response(
                content=cached,
                media_type="application/json",
                headers={"X-Cache": "HIT"},
            )

    try:
        # GEOSEARCH devuelve [[member, distance], ...] ordenado por distancia.
        results = rdb.geosearch(
            GEO_KEY,
            longitude=lng,
            latitude=lat,
            radius=effective_radius,
            unit="m",
            withdist=True,
            sort="ASC",
        )
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    results = results or []
    ids_in_radius = [row[0] for row in results]
    distance_by_id = {row[0]: float(row[1]) for row in results}

    try:
        places = _load_places(rdb, ids_in_radius)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    filtered = apply_filters(
        places,
        ids=set(ids) if ids else None,
        normalized_q=normalize_for_search(q) if q else None,
        vehicle_types=set(vehicleType) if vehicleType else None,
        categories=set(category) if category else None,
        regulations=set(regulation) if regulation else None,
        min_spaces=minSpaces,
    )

    out = [
        ParkingPlaceNearbyOut(
            **place.model_dump(),
            distanceMeters=distance_by_id[place.id],
        )
        for place in filtered
    ]

    if cache_enabled:
        try:
            payload = json.dumps([p.model_dump(mode="json") for p in out])
            rdb.setex(cache_key, CACHE_NEARBY_TTL, payload)
        except redis.ConnectionError:
            logger.warning("No se pudo escribir caché %s (Redis no disponible)", cache_key)

    response.headers["X-Cache"] = "MISS" if cache_enabled else "BYPASS"
    return out


# ============================================================
# GET /parkings/categories — catálogo de categorías presentes
# ============================================================

@router.get(
    "/categories",
    response_model=list[ParkingCategory],
    summary="Categorías presentes en el catálogo",
    description=(
        "Devuelve la lista de `ParkingCategory` que tienen al menos un "
        "aparcamiento en Redis, ordenadas por orden de declaración del enum "
        "(idéntico a `LocalParkingRepository.getCategories` en Flutter)."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"example": _CATEGORIES_EXAMPLE}
            }
        }
    },
)
def list_categories(rdb: redis.Redis = Depends(get_redis)):
    try:
        all_ids = _scan_all_ids(rdb)
        places = _load_places(rdb, all_ids)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    present = {p.category for p in places}
    # Orden por declaración del enum: equivalente a `a.index.compareTo(b.index)`.
    return [c for c in ParkingCategory if c in present]


# ============================================================
# GET /parkings/{parking_id} — detalle (DEBE ir al final del archivo)
# ============================================================

@router.get(
    "/{parking_id}",
    response_model=ParkingPlaceOut,
    summary="Detalle de un aparcamiento",
    description="Devuelve un único `ParkingPlace` por id. 404 si no existe.",
    responses={
        200: {
            "content": {
                "application/json": {"example": _PLACE_POLYGON_EXAMPLE}
            }
        },
        404: {"description": "El aparcamiento no existe en Redis."},
    },
)
def get_parking(
    parking_id: str,
    rdb: redis.Redis = Depends(get_redis),
):
    try:
        data = rdb.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Aparcamiento {parking_id!r} no encontrado",
        )

    return place_from_redis_hash(data)
