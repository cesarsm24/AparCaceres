"""Favoritos persistentes por usuario.

Solución pragmática sin sistema de auth real: el cliente identifica al usuario
con la cabecera HTTP `X-User-Id`. Por usuario guardamos un sorted set
`user:{user_id}:favorites` con score = epoch ms del momento en que se favoritó.
`ZREVRANGE` nos da los favoritos newest-first listos para la pantalla.

Reglas:
- `PUT` y `DELETE` validan que el aparcamiento existe en el catálogo (404 si
  no existe). Así un id basura nunca contamina la lista de favoritos del
  usuario.
- `PUT` es idempotente: si ya estaba, no se reescribe la marca temporal (la
  posición no salta cada vez que el cliente reenvía la petición).
- `DELETE` es idempotente: si el aparcamiento existe pero no estaba en
  favoritos, devuelve 200 con `removed=False` en vez de 404.
- `GET` devuelve directamente `list[ParkingPlaceOut]` (mismo shape que
  `/parkings`) para alimentar la pantalla de favoritos sin más adaptación.
  Si un favorito apunta a un aparcamiento que ya no existe en el catálogo
  se descarta silenciosamente (degradación suave; el cliente no ve huecos).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import redis
from fastapi import APIRouter, Depends, Header, HTTPException

from ..config import (
    PARKING_KEY_PREFIX,
    USER_FAVORITES_KEY_PREFIX,
    USER_FAVORITES_KEY_SUFFIX,
)
from ..importer import place_from_redis_hash
from ..redis_client import get_redis, raise_redis_503
from ..schemas import FavoriteAdded, FavoriteRemoved, ParkingPlaceOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users/me/favorites", tags=["favorites"])


# ============================================================
# Validación del header X-User-Id
# ============================================================

# Caracteres prohibidos en el user-id: los que romperían la clave de Redis
# (`:` separa segmentos, `*?[]` son comodines de KEYS/SCAN) más whitespace.
_FORBIDDEN_USER_ID_CHARS = frozenset(":*?[] \t\n\r")
_USER_ID_MAX_LEN = 128


def require_user_id(
    x_user_id: Optional[str] = Header(
        None,
        alias="X-User-Id",
        description="Identificador opaco del usuario. Pragmatismo: sin auth real.",
    ),
) -> str:
    """Dependency: extrae y valida `X-User-Id`.

    400 (no 422) cuando falta o está mal formado, para que el cliente lo
    distinga de errores de validación de body/query.
    """
    if x_user_id is None:
        raise HTTPException(status_code=400, detail="Falta cabecera X-User-Id")
    user_id = x_user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Cabecera X-User-Id vacía")
    if len(user_id) > _USER_ID_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"X-User-Id excede {_USER_ID_MAX_LEN} caracteres",
        )
    if any(c in _FORBIDDEN_USER_ID_CHARS for c in user_id):
        raise HTTPException(
            status_code=400,
            detail="X-User-Id contiene caracteres inválidos (espacios o ':*?[]')",
        )
    return user_id


# ============================================================
# Helpers internos
# ============================================================

def _favorites_key(user_id: str) -> str:
    return f"{USER_FAVORITES_KEY_PREFIX}{user_id}{USER_FAVORITES_KEY_SUFFIX}"


def _now_ms() -> int:
    """Epoch ms en UTC. Se monkeypatchea desde los tests para fijar el orden."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _ensure_parking_exists(rdb: redis.Redis, parking_id: str) -> None:
    """Lanza 404 si `parking:{id}` no existe en Redis."""
    try:
        exists = rdb.exists(f"{PARKING_KEY_PREFIX}{parking_id}")
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Aparcamiento {parking_id!r} no encontrado",
        )


# ============================================================
# Ejemplos OpenAPI
# ============================================================

_FAVORITES_LIST_EXAMPLE = [
    {
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
    },
    {
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
    },
]

_FAVORITE_ADDED_EXAMPLE = {
    "id": "aparcamiento-5500",
    "addedAt": "2026-04-25T19:30:00+00:00",
    "created": True,
}

_FAVORITE_REMOVED_EXAMPLE = {
    "id": "aparcamiento-5500",
    "removed": True,
}


# ============================================================
# GET /users/me/favorites
# ============================================================

@router.get(
    "",
    response_model=list[ParkingPlaceOut],
    summary="Lista los favoritos del usuario, más recientes primero",
    description=(
        "Devuelve los aparcamientos favoritos del usuario identificado por "
        "`X-User-Id`, ordenados por fecha de adición descendente "
        "(`ZREVRANGE` sobre el sorted set `user:{userId}:favorites`).\n\n"
        "El payload es directamente `list[ParkingPlace]` con el mismo shape "
        "que `/parkings`, listo para alimentar la pantalla de favoritos.\n\n"
        "Si la lista contiene un id cuyo `parking:{id}` ha sido borrado del "
        "catálogo (p. ej. tras un `/import-parkings` que descarta entradas), "
        "la entrada se omite silenciosamente: el cliente nunca ve huecos."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"example": _FAVORITES_LIST_EXAMPLE}
            }
        },
        400: {"description": "Falta o es inválida la cabecera X-User-Id."},
    },
)
def list_favorites(
    user_id: str = Depends(require_user_id),
    rdb: redis.Redis = Depends(get_redis),
):
    key = _favorites_key(user_id)
    try:
        # ZREVRANGE 0 -1 → todos los miembros, score descendente (más reciente primero).
        ids = rdb.zrevrange(key, 0, -1)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    if not ids:
        return []

    # Pipeline para minimizar round-trips al recuperar los hashes.
    pipe = rdb.pipeline()
    for pid in ids:
        pipe.hgetall(f"{PARKING_KEY_PREFIX}{pid}")
    try:
        hashes = pipe.execute()
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    out: list[ParkingPlaceOut] = []
    for pid, data in zip(ids, hashes):
        if not data:
            # Favorito huérfano: el aparcamiento ya no existe. No es un error,
            # solo lo saltamos (el cliente nunca se entera).
            logger.warning(
                "Favorito %s del usuario %s sin parking en catálogo; saltando",
                pid,
                user_id,
            )
            continue
        out.append(place_from_redis_hash(data))
    return out


# ============================================================
# PUT /users/me/favorites/{parking_id}
# ============================================================

@router.put(
    "/{parking_id}",
    response_model=FavoriteAdded,
    summary="Marca un aparcamiento como favorito",
    description=(
        "Añade `parkingId` a los favoritos del usuario. Idempotente: si ya "
        "estaba, conservamos la marca temporal original para que el orden "
        "no salte al re-PUT.\n\n"
        "El score del sorted set es el epoch ms del momento de adición; el "
        "campo `addedAt` lo expone como ISO 8601 UTC para el cliente."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"example": _FAVORITE_ADDED_EXAMPLE}
            }
        },
        400: {"description": "Falta o es inválida la cabecera X-User-Id."},
        404: {"description": "El aparcamiento no existe en el catálogo."},
    },
)
def add_favorite(
    parking_id: str,
    user_id: str = Depends(require_user_id),
    rdb: redis.Redis = Depends(get_redis),
):
    _ensure_parking_exists(rdb, parking_id)

    key = _favorites_key(user_id)
    try:
        existing = rdb.zscore(key, parking_id)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    if existing is not None:
        # Ya estaba: respetamos el timestamp original (idempotencia "estable").
        added_ms = int(existing)
        created = False
    else:
        added_ms = _now_ms()
        try:
            rdb.zadd(key, {parking_id: added_ms})
        except redis.ConnectionError as exc:
            raise raise_redis_503(exc) from exc
        created = True

    return FavoriteAdded(
        id=parking_id,
        addedAt=_ms_to_iso(added_ms),
        created=created,
    )


# ============================================================
# DELETE /users/me/favorites/{parking_id}
# ============================================================

@router.delete(
    "/{parking_id}",
    response_model=FavoriteRemoved,
    summary="Quita un aparcamiento de favoritos",
    description=(
        "Quita `parkingId` de los favoritos del usuario. Idempotente: si el "
        "aparcamiento existe en el catálogo pero no estaba en la lista del "
        "usuario, devolvemos 200 con `removed=False`.\n\n"
        "Devuelve 404 cuando `parkingId` no existe en el catálogo, igual que "
        "el PUT, para que un id basura no se pueda 'borrar'."
    ),
    responses={
        200: {
            "content": {
                "application/json": {"example": _FAVORITE_REMOVED_EXAMPLE}
            }
        },
        400: {"description": "Falta o es inválida la cabecera X-User-Id."},
        404: {"description": "El aparcamiento no existe en el catálogo."},
    },
)
def remove_favorite(
    parking_id: str,
    user_id: str = Depends(require_user_id),
    rdb: redis.Redis = Depends(get_redis),
):
    _ensure_parking_exists(rdb, parking_id)

    key = _favorites_key(user_id)
    try:
        removed = rdb.zrem(key, parking_id)
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    return FavoriteRemoved(id=parking_id, removed=bool(removed))
