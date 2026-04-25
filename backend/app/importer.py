"""Importador del dataset municipal al contrato móvil + Redis.

Capa intermedia entre `data/aparcamientos.geojson` (Open Data Cáceres) y la
representación que consume Flutter (`ParkingPlaceOut`):

- `feature_to_place` mapea un Feature GeoJSON -> `ParkingPlaceOut`, derivando
  un id estable a partir del `mslink` de la URL del dataset.
- `place_to_redis_mapping` aplana el modelo a un dict apto para `HSET` (solo
  strings; los `None` se omiten para que la lectura los recupere como ausentes
  y los validators los devuelvan como `null`).
- `place_from_redis_hash` reconstruye el modelo desde un hash de Redis,
  re-parseando `coordinates` (que va serializado como JSON dentro del hash).
- `run_import` orquesta el ciclo completo (limpieza idempotente, GEOADD+HSET
  pipelined e invalidación de caché). Aislado de FastAPI para que sea
  fácilmente testeable contra un fake de Redis.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Optional

import redis

from .config import CACHE_NEARBY_PREFIX, GEO_KEY, PARKING_KEY_PREFIX
from .enums import ParkingGeometryType
from .normalization import coerce_line_string, coerce_polygon
from .schemas import ParkingPlaceOut

logger = logging.getLogger(__name__)


# GeoJSON geometry.type -> miembro del enum del contrato móvil.
# Multi* no se soporta: el dataset municipal no los usa y mezclar tipos en un
# único Feature romperia el contrato (cada place = una sola geometría).
_GEOJSON_TYPE_TO_GEOMETRY: dict[str, ParkingGeometryType] = {
    "Point": ParkingGeometryType.POINT,
    "Polygon": ParkingGeometryType.POLYGON,
    "LineString": ParkingGeometryType.LINE_STRING,
}

# El dataset municipal expone un identificador estable como query param de la
# URL de la ficha: http://sig.caceres.es/.../fichatoponimia.php?mslink=1903
# Lo usamos como base del id para que sobreviva a reordenaciones del fichero
# (a diferencia del índice posicional usado antes).
_MSLINK_RE = re.compile(r"mslink=(\d+)")

# Campos que se serializan al hash de Redis. Mantener sincronizado con
# `ParkingPlaceOut`. `coordinates` se trata aparte porque va como JSON.
_HASH_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "vehicleType",
    "regulation",
    "geometryType",
    "latitude",
    "longitude",
    "totalSpaces",
    "streetName",
    "streetType",
    "district",
    "neighborhood",
    "sourceDataset",
    "imageUrl",
    "urlFicha",
    "urlVia",
    "management",
)


# ============================================================
# Derivación de id y punto representativo
# ============================================================

def derive_stable_id(properties: dict) -> Optional[str]:
    """Extrae un id estable de las properties del Feature.

    Preferencia: `mslink` de la URL (presente en todo el dataset municipal).
    Fallback: campo `id` explícito si llega del dataset.
    Devuelve `None` si no se puede derivar — ese feature se descartará.
    """
    url = properties.get("URL") or properties.get("url") or ""
    match = _MSLINK_RE.search(str(url))
    if match:
        return f"aparcamiento-{match.group(1)}"

    explicit = properties.get("id") or properties.get("ID")
    if explicit not in (None, ""):
        return str(explicit).strip() or None

    return None


def representative_point(
    geometry_type: ParkingGeometryType,
    raw_coords: object,
) -> Optional[tuple[float, float]]:
    """Devuelve un `(lon, lat)` representativo para indexar en `geo:parkings`.

    - POINT: la propia coordenada.
    - POLYGON: centroide simple del primer anillo (excluyendo el cierre duplicado).
    - LINE_STRING: punto medio por índice del trazo.

    `None` si la geometría no aporta un punto válido (se descarta el feature).
    """
    if geometry_type is ParkingGeometryType.POINT:
        if not isinstance(raw_coords, (list, tuple)) or len(raw_coords) < 2:
            return None
        try:
            return (float(raw_coords[0]), float(raw_coords[1]))
        except (TypeError, ValueError):
            return None

    if geometry_type is ParkingGeometryType.POLYGON:
        polygon = coerce_polygon(raw_coords)
        if not polygon:
            return None
        ring = polygon[0]
        # Anillo cerrado: el primer y último punto coinciden; lo descartamos
        # para no sesgar el promedio.
        pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
        if not pts:
            return None
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        return (lon, lat)

    if geometry_type is ParkingGeometryType.LINE_STRING:
        line = coerce_line_string(raw_coords)
        if not line:
            return None
        return line[len(line) // 2]

    return None


# ============================================================
# Feature -> ParkingPlaceOut
# ============================================================

def feature_to_place(feature: dict) -> Optional[ParkingPlaceOut]:
    """Convierte un Feature GeoJSON al contrato móvil.

    Devuelve `None` cuando el feature no se puede importar (sin geometría
    soportada, sin id estable o con coordenadas degeneradas). El llamador
    cuenta los descartes para reportarlos en la respuesta del endpoint.
    """
    geometry = feature.get("geometry") or {}
    properties = feature.get("properties") or {}

    geom_type = _GEOJSON_TYPE_TO_GEOMETRY.get(geometry.get("type"))
    if geom_type is None:
        return None

    raw_coords = geometry.get("coordinates")
    point = representative_point(geom_type, raw_coords)
    if point is None:
        return None
    lon, lat = point

    parking_id = derive_stable_id(properties)
    if parking_id is None:
        return None

    # El dataset municipal usa propiedades en MAYÚSCULAS y castellano. Si en el
    # futuro llega un dataset que ya viene en formato wire (camelCase), las
    # claves modernas tienen prioridad para no perder información.
    return ParkingPlaceOut(
        id=parking_id,
        name=properties.get("name") or properties.get("NOMBRE") or "",
        category=properties.get("category"),
        vehicleType=properties.get("vehicleType"),
        regulation=properties.get("regulation"),
        geometryType=geom_type,
        latitude=lat,
        longitude=lon,
        # Para POINT el validator descarta `coordinates`; lo pasamos igualmente
        # por simetría con POLYGON / LINE_STRING.
        coordinates=raw_coords,
        totalSpaces=(
            properties.get("totalSpaces")
            or properties.get("TOTAL_SPACES")
            or properties.get("PLAZAS")
        ),
        streetName=properties.get("streetName") or properties.get("DIRECCION"),
        streetType=properties.get("streetType"),
        district=properties.get("district") or properties.get("NUCLEO"),
        neighborhood=properties.get("neighborhood"),
        sourceDataset=properties.get("sourceDataset"),
        imageUrl=properties.get("imageUrl"),
        urlFicha=properties.get("urlFicha") or properties.get("URL"),
        urlVia=properties.get("urlVia"),
        management=properties.get("management") or properties.get("GESTION"),
    )


# ============================================================
# ParkingPlaceOut <-> hash de Redis
# ============================================================

def place_to_redis_mapping(place: ParkingPlaceOut) -> dict[str, str]:
    """Aplana un `ParkingPlaceOut` a un dict apto para `HSET`.

    Reglas:
    - Solo strings (Redis hashes no almacenan otra cosa cuando `decode_responses=True`).
    - Enums -> wire string (`.value`).
    - `coordinates` se serializa como JSON; se omite para POINT (siempre `None`).
    - Campos `None` se omiten del mapping para que en lectura el contrato los
      recupere como ausentes y los normalice a `null`.
    """
    # `mode="json"` hace que los enums se serialicen como su `.value` (wire string)
    # y que `coordinates` salga ya como lista JSON-compatible.
    dumped = place.model_dump(mode="json")
    out: dict[str, str] = {}
    for field in _HASH_FIELDS:
        value = dumped.get(field)
        if value is None:
            continue
        out[field] = str(value)

    coords = dumped.get("coordinates")
    if coords is not None:
        out["coordinates"] = json.dumps(coords)

    return out


def place_from_redis_hash(data: dict[str, str]) -> ParkingPlaceOut:
    """Reconstruye un `ParkingPlaceOut` desde un hash leído con `HGETALL`.

    Inversa de `place_to_redis_mapping`: re-parsea `coordinates` (JSON) y deja
    que los validators del schema se encarguen del resto (str -> int/float,
    enums lenient, opcionales vacíos -> `None`).
    """
    payload: dict[str, Any] = dict(data)
    if "coordinates" in payload:
        try:
            payload["coordinates"] = json.loads(payload["coordinates"])
        except (TypeError, ValueError):
            # Hash corrupto: dejamos que el validator caiga al default ([] o None).
            payload["coordinates"] = None
    return ParkingPlaceOut(**payload)


# ============================================================
# Orquestador del import (sin FastAPI para que sea testeable)
# ============================================================

def run_import(features: Iterable[dict], rdb: redis.Redis) -> dict[str, Any]:
    """Aplica el import completo sobre `rdb`. Idempotente.

    1. Borra todos los hashes `parking:*` del import previo (SCAN_ITER + DEL).
    2. Borra el sorted set `geo:parkings`.
    3. Por cada feature válido: GEOADD al índice geo + HSET con el contrato
       completo. Todo en un único pipeline para minimizar round-trips.
    4. Invalida la caché `cache:nearby:*` (best-effort: si Redis falla aquí,
       el TTL acabará limpiándola).

    Devuelve un dict con el resumen para que el endpoint lo serialice.
    Las `redis.ConnectionError` se propagan tal cual; el router las traducirá
    a HTTP 503.
    """
    # Materializamos para poder contar y para evitar reabrir la pipeline si
    # el caller pasa un generador.
    features = list(features)

    old_keys = list(rdb.scan_iter(match=f"{PARKING_KEY_PREFIX}*"))

    pipe = rdb.pipeline()
    if old_keys:
        pipe.delete(*old_keys)
    pipe.delete(GEO_KEY)

    imported = 0
    skipped = 0
    seen_ids: set[str] = set()

    for feature in features:
        place = feature_to_place(feature)
        if place is None:
            skipped += 1
            continue

        if place.id in seen_ids:
            # Dataset con mslink duplicado: el segundo gana (HSET sobreescribe).
            # Lo registramos para que sea visible en logs sin romper el import.
            logger.warning("id duplicado %r en el dataset; sobreescribiendo", place.id)
        seen_ids.add(place.id)

        pipe.geoadd(GEO_KEY, (place.longitude, place.latitude, place.id))
        pipe.hset(
            f"{PARKING_KEY_PREFIX}{place.id}",
            mapping=place_to_redis_mapping(place),
        )
        imported += 1

    pipe.execute()

    # Invalidación de caché: best-effort. Si falla, el TTL hará el trabajo.
    try:
        cache_keys = list(rdb.scan_iter(match=f"{CACHE_NEARBY_PREFIX}*"))
        if cache_keys:
            rdb.delete(*cache_keys)
    except redis.ConnectionError:
        logger.warning("No se pudo invalidar cache:nearby:* al reimportar")
        cache_keys = []

    return {
        "status": "ok",
        "imported": imported,
        "skipped": skipped,
        "geo_key": GEO_KEY,
        "cache_invalidated": len(cache_keys),
    }
