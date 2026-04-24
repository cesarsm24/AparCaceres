import json
import logging

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..config import CACHE_NEARBY_PREFIX, CACHE_NEARBY_TTL, GEO_KEY, PARKING_KEY_PREFIX
from ..redis_client import get_redis, raise_redis_503
from ..schemas import Parking, ParkingNearby

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parkings", tags=["parkings"])


# OJO con el orden de rutas: `/parkings/nearby` debe declararse ANTES que
# `/parkings/{parking_id}`; si no, FastAPI capturaría "nearby" como un id.

@router.get("/nearby", response_model=list[ParkingNearby])
def get_parkings_nearby(
    response: Response,
    lat: float = Query(..., description="Latitud del punto de búsqueda"),
    lng: float = Query(..., description="Longitud del punto de búsqueda"),
    radius: float = Query(1000, ge=0, description="Radio en metros (por defecto 1000)"),
    rdb: redis.Redis = Depends(get_redis),
):
    """Devuelve los aparcamientos dentro de `radius` metros, ordenados por distancia.

    Cacheado en Redis con clave `cache:nearby:{lat}:{lng}:{radius}` y TTL
    `CACHE_NEARBY_TTL` (segundos). Se redondean lat/lng a 4 decimales (~10m) para
    que peticiones casi-iguales reutilicen la misma entrada de caché.
    """
    # Clave de caché estable: redondeo controlado de los parámetros.
    cache_key = f"{CACHE_NEARBY_PREFIX}{lat:.4f}:{lng:.4f}:{int(radius)}"
    cache_enabled = CACHE_NEARBY_TTL > 0

    # --- Intento de HIT (look-aside) ---
    if cache_enabled:
        try:
            # GET devuelve el string cacheado (None si no hay clave o ha expirado).
            cached = rdb.get(cache_key)
        except redis.ConnectionError:
            # Degradación suave: si Redis no responde al leer caché, seguimos al cómputo.
            cached = None

        if cached is not None:
            # Fast path: devolvemos el JSON tal cual, saltando Pydantic/response_model.
            # Añadimos X-Cache para que sea fácil ver en dev si pegó caché.
            return Response(
                content=cached,
                media_type="application/json",
                headers={"X-Cache": "HIT"},
            )

    # --- MISS: calculamos el resultado desde Redis ---
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
        raise raise_redis_503(exc) from exc

    if results:
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
            raise raise_redis_503(exc) from exc

        out: list[ParkingNearby] = []
        for parking_id, dist, data in zip(ids, distances, hashes):
            if not data:
                # Miembro presente en geo:parkings pero sin hash asociado -> lo saltamos.
                logger.warning("parking:%s está en geo pero no tiene hash", parking_id)
                continue
            out.append(ParkingNearby(**data, distancia_metros=dist))
    else:
        out = []

    # --- Guardar en caché (best-effort) ---
    if cache_enabled:
        try:
            payload = json.dumps([p.model_dump() for p in out])
            # SETEX key ttl value -> SET con TTL en segundos atómicamente.
            rdb.setex(cache_key, CACHE_NEARBY_TTL, payload)
        except redis.ConnectionError:
            # No bloqueamos la respuesta si falla escribir la caché.
            logger.warning("No se pudo escribir en caché %s (Redis no disponible)", cache_key)

    response.headers["X-Cache"] = "MISS" if cache_enabled else "BYPASS"
    return out


@router.get("/{parking_id}", response_model=Parking)
def get_parking(parking_id: str, rdb: redis.Redis = Depends(get_redis)):
    """Devuelve el detalle de un aparcamiento leyendo su hash `parking:{id}`."""
    try:
        # HGETALL: devuelve todos los campos del hash como dict (vacío si no existe).
        data = rdb.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")
    except redis.ConnectionError as exc:
        raise raise_redis_503(exc) from exc

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Aparcamiento {parking_id!r} no encontrado",
        )

    return Parking(**data)
