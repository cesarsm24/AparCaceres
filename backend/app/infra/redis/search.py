"""Búsqueda del catálogo de aparcamientos.

Esta capa traduce el contrato de consulta del backend a RediSearch. En
producción, Redis Stack actúa como motor de búsqueda: el índice almacena lo
necesario para filtrar por tags, texto libre, geolocalización y ordenación por
distancia.

La capa no degrada a una implementación alternativa si RediSearch no está
disponible. En ese caso se propaga un error de configuración o disponibilidad
para que el servicio falle de forma explícita.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import redis
from redis.exceptions import ResponseError

from ...core.config import (
    PARKING_KEY_PREFIX,
    SEARCH_INDEX_NAME,
)
from ...enums import (
    ParkingCategory,
    ParkingRegulation,
    ParkingVehicleType,
)
from ...filters import apply_filters, normalize_for_search
from ...schemas import ParkingFacetsOut, ParkingPlaceNearbyOut, ParkingPlaceOut

_EARTH_RADIUS_M = 6_371_000.0
_TEXT_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class SearchIndexError(RuntimeError):
    """Error de configuración o disponibilidad de RediSearch.

    Se usa para diferenciar fallos de consulta ordinarios de una instalación
    incompleta del módulo de búsqueda.
    """


@dataclass(frozen=True)
class ParkingSearchResult:
    """Resultado paginado de búsqueda de aparcamientos.

    `total` refleja el conjunto completo que satisface el filtro; `items`
    contiene solo la ventana pedida por `offset` y `limit`.
    """

    items: list[ParkingPlaceOut]
    total: int


@dataclass(frozen=True)
class ParkingNearbySearchResult:
    """Resultado paginado de búsqueda geográfica de aparcamientos.

    Mantiene el mismo patrón de paginación que `ParkingSearchResult`, pero
    incorpora la distancia calculada por RediSearch para cada elemento.
    """

    items: list[ParkingPlaceNearbyOut]
    total: int


def build_search_text(place: ParkingPlaceOut) -> str:
    """Construye el texto indexable para búsqueda libre.

    Solo incluye campos descriptivos y el dataset de origen para que el campo
    `TEXT` represente lenguaje natural. Las dimensiones filtrables se dejan
    fuera a propósito y se expresan como `TAG` independientes.
    """
    values = [
        place.name,
        place.streetName,
        place.streetType,
        place.district,
        place.neighborhood,
        place.sourceDataset,
    ]
    return normalize_for_search(" ".join(value for value in values if value))


def build_location(place: ParkingPlaceOut) -> str:
    """Devuelve la ubicación en formato GEO de RediSearch."""
    return f"{place.longitude},{place.latitude}"


def recreate_search_index(
    rdb: redis.Redis,
    *,
    name: str = SEARCH_INDEX_NAME,
    key_prefix: str = PARKING_KEY_PREFIX,
) -> None:
    """Recrea un índice RediSearch sin eliminar los hashes indexados.

    Se usa durante el import con doble buffer para construir una generación
    nueva sobre un prefijo distinto y luego sustituir el catálogo activo.
    """
    if not hasattr(rdb, "execute_command"):
        return

    try:
        rdb.execute_command("FT.DROPINDEX", name)
    except ResponseError as exc:
        if not _is_unknown_index(exc):
            _raise_stack_error(exc)

    _create_search_index(rdb, name=name, key_prefix=key_prefix)


def drop_search_index(rdb: redis.Redis, *, name: str) -> None:
    """Elimina un índice RediSearch de forma idempotente.

    No borra los hashes, solo la metadata del índice. La operación tolera que
    el índice ya no exista para simplificar los swaps del importador.
    """
    if not hasattr(rdb, "execute_command"):
        return

    try:
        rdb.execute_command("FT.DROPINDEX", name)
    except ResponseError as exc:
        if not _is_unknown_index(exc):
            _raise_stack_error(exc)


def ensure_search_index(rdb: redis.Redis) -> None:
    """Garantiza que el índice principal de búsqueda existe.

    El arranque del backend lo llama para autocurar una instalación nueva
    cuando el índice todavía no ha sido creado.
    """
    if not hasattr(rdb, "execute_command"):
        return

    try:
        rdb.execute_command("FT.INFO", SEARCH_INDEX_NAME)
    except ResponseError as exc:
        if _is_unknown_index(exc):
            _create_search_index(rdb)
            return

        _raise_stack_error(exc)


def search_parkings(
    rdb: redis.Redis,
    *,
    ids: Optional[Iterable[str]] = None,
    q: Optional[str] = None,
    vehicle_types: Optional[Iterable[ParkingVehicleType]] = None,
    categories: Optional[Iterable[ParkingCategory]] = None,
    regulations: Optional[Iterable[ParkingRegulation]] = None,
    datasets: Optional[Iterable[str]] = None,
    min_spaces: int = 0,
    offset: int = 0,
    limit: int = 100,
) -> ParkingSearchResult:
    """Busca aparcamientos mediante filtros indexados.

    La consulta combina texto libre, tags y filtros numéricos. Si el servidor
    no soporta RediSearch, la función falla de forma explícita con un error de
    configuración.
    """
    _require_redisearch(rdb)

    query = _build_query(
        ids=ids,
        q=q,
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
    )
    total, places = _ft_search_with_payload(rdb, query, offset=offset, limit=limit)
    return ParkingSearchResult(items=places, total=total)


def search_nearby(
    rdb: redis.Redis,
    *,
    lat: float,
    lng: float,
    radius_meters: float,
    ids: Optional[Iterable[str]] = None,
    q: Optional[str] = None,
    vehicle_types: Optional[Iterable[ParkingVehicleType]] = None,
    categories: Optional[Iterable[ParkingCategory]] = None,
    regulations: Optional[Iterable[ParkingRegulation]] = None,
    datasets: Optional[Iterable[str]] = None,
    min_spaces: int = 0,
    offset: int = 0,
    limit: int = 100,
) -> ParkingNearbySearchResult:
    """Busca aparcamientos dentro de un radio y los ordena por distancia.

    RediSearch calcula la distancia en el propio query y devuelve ya el
    subconjunto paginado ordenado de forma ascendente.
    """
    _require_redisearch(rdb)

    query = _build_query(
        ids=ids,
        q=q,
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
        geo=(lng, lat, radius_meters),
    )
    total, nearby = _ft_nearby_rows(
        rdb,
        query=query,
        lng=lng,
        lat=lat,
        offset=offset,
        limit=limit,
    )
    return ParkingNearbySearchResult(items=nearby, total=total)


def search_in_bounds(
    rdb: redis.Redis,
    *,
    min_lat: float,
    min_lng: float,
    max_lat: float,
    max_lng: float,
    vehicle_types: Optional[Iterable[ParkingVehicleType]] = None,
    categories: Optional[Iterable[ParkingCategory]] = None,
    regulations: Optional[Iterable[ParkingRegulation]] = None,
    datasets: Optional[Iterable[str]] = None,
    min_spaces: int = 0,
    offset: int = 0,
    limit: int = 100,
) -> ParkingSearchResult:
    """Busca aparcamientos dentro de un rectángulo geográfico.

    Se usa para consultas de viewport del mapa, donde el backend debe
    recortar por límites de latitud y longitud antes de aplicar los demás
    filtros.
    """
    _require_redisearch(rdb)

    query = _build_query(
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
        bounds=(min_lat, min_lng, max_lat, max_lng),
    )
    total, places = _ft_search_with_payload(rdb, query, offset=offset, limit=limit)
    return ParkingSearchResult(items=places, total=total)


def get_facets(rdb: redis.Redis) -> ParkingFacetsOut:
    """Obtiene conteos agregados por dimensiones filtrables.

    Calcula facetas globales por categoría, vehículo, regulación y dataset
    para alimentar filtros de interfaz sin duplicar lógica en Flutter.
    """
    _require_redisearch(rdb)

    total, _ = _ft_search_ids(rdb, "*", offset=0, limit=0)
    return ParkingFacetsOut(
        total=total,
        categories=_aggregate_tag_counts(rdb, "category"),
        vehicleTypes=_aggregate_tag_counts(rdb, "vehicleType"),
        regulations=_aggregate_tag_counts(rdb, "regulation"),
        datasets=_aggregate_tag_counts(rdb, "sourceDataset"),
    )


def _create_search_index(
    rdb: redis.Redis,
    *,
    name: str = SEARCH_INDEX_NAME,
    key_prefix: str = PARKING_KEY_PREFIX,
) -> None:
    try:
        rdb.execute_command(
            "FT.CREATE",
            name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            key_prefix,
            "SCHEMA",
            "id",
            "TAG",
            "category",
            "TAG",
            "vehicleType",
            "TAG",
            "regulation",
            "TAG",
            "sourceDataset",
            "TAG",
            "location",
            "GEO",
            "latitude",
            "NUMERIC",
            "longitude",
            "NUMERIC",
            "totalSpaces",
            "NUMERIC",
            "searchText",
            "TEXT",
            "NOSTEM",
        )
    except ResponseError as exc:
        _raise_stack_error(exc)


def _require_redisearch(rdb: redis.Redis) -> None:
    if hasattr(rdb, "execute_command"):
        return

    raise SearchIndexError("Redis Stack / RediSearch es obligatorio en producción")


def _is_unknown_index(exc: ResponseError) -> bool:
    msg = str(exc).lower()
    return "unknown index" in msg or "no such index" in msg or "index does not exist" in msg


def _raise_stack_error(exc: ResponseError) -> None:
    msg = str(exc).lower()
    if "unknown command" in msg or "module" in msg:
        raise SearchIndexError("Redis Stack / RediSearch es obligatorio en producción") from exc

    raise exc


def _ft_search_ids(
    rdb: redis.Redis,
    query: str,
    *,
    offset: int,
    limit: int,
) -> tuple[int, list[str]]:
    """Ejecuta una búsqueda sin payload y devuelve ids de aparcamiento."""
    ensure_search_index(rdb)

    try:
        resp = rdb.execute_command(
            "FT.SEARCH",
            SEARCH_INDEX_NAME,
            query,
            "NOCONTENT",
            "LIMIT",
            offset,
            limit,
            "DIALECT",
            "2",
        )
    except ResponseError as exc:
        _raise_stack_error(exc)

    if not resp:
        return 0, []

    total = int(resp[0])
    return total, [_key_to_id(key) for key in resp[1:]]


def _ft_search_with_payload(
    rdb: redis.Redis,
    query: str,
    *,
    offset: int,
    limit: int,
) -> tuple[int, list[ParkingPlaceOut]]:
    """Ejecuta una búsqueda RediSearch y reconstruye modelos desde el payload."""
    ensure_search_index(rdb)

    if limit == 0:
        total, _ = _ft_search_ids(rdb, query, offset=0, limit=0)
        return total, []

    try:
        resp = rdb.execute_command(
            "FT.SEARCH",
            SEARCH_INDEX_NAME,
            query,
            "LIMIT",
            offset,
            limit,
            "DIALECT",
            "2",
        )
    except ResponseError as exc:
        _raise_stack_error(exc)

    if not resp:
        return 0, []

    from .importer import place_from_redis_hash

    total = int(resp[0])
    places: list[ParkingPlaceOut] = []
    body = resp[1:]

    for index in range(0, len(body) - 1, 2):
        fields = body[index + 1]
        data = _row_to_dict(fields)
        if data:
            places.append(place_from_redis_hash(data))

    return total, places


def _ft_nearby_rows(
    rdb: redis.Redis,
    *,
    query: str,
    lng: float,
    lat: float,
    offset: int,
    limit: int,
) -> tuple[int, list[ParkingPlaceNearbyOut]]:
    """Ejecuta búsqueda geográfica ordenada por distancia en RediSearch.

    Se carga el hash completo junto al campo calculado `distance` para evitar
    llamadas adicionales por resultado.
    """
    ensure_search_index(rdb)
    sort_window = max(offset + limit, limit)

    try:
        resp = rdb.execute_command(
            "FT.AGGREGATE",
            SEARCH_INDEX_NAME,
            query,
            "LOAD",
            "*",
            "APPLY",
            f"geodistance(@location,{float(lng)},{float(lat)})",
            "AS",
            "distance",
            "SORTBY",
            "2",
            "@distance",
            "ASC",
            "MAX",
            sort_window,
            "LIMIT",
            offset,
            limit,
            "DIALECT",
            "2",
        )
    except ResponseError as exc:
        _raise_stack_error(exc)

    if not resp:
        return 0, []

    from .importer import place_from_redis_hash

    nearby: list[ParkingPlaceNearbyOut] = []

    for row in resp[1:]:
        values = _row_to_dict(row)
        if not values:
            continue

        try:
            distance = float(values.get("distance", 0))
        except (TypeError, ValueError):
            distance = 0.0

        values.pop("distance", None)

        try:
            place = place_from_redis_hash(values)
        except Exception:  # noqa: BLE001
            continue

        nearby.append(
            ParkingPlaceNearbyOut(
                **place.model_dump(),
                distanceMeters=distance,
            )
        )

    return int(resp[0]), nearby


def _aggregate_tag_counts(rdb: redis.Redis, field: str) -> dict[str, int]:
    try:
        resp = rdb.execute_command(
            "FT.AGGREGATE",
            SEARCH_INDEX_NAME,
            "*",
            "GROUPBY",
            "1",
            f"@{field}",
            "REDUCE",
            "COUNT",
            "0",
            "AS",
            "count",
            "LIMIT",
            "0",
            "1000",
            "DIALECT",
            "2",
        )
    except ResponseError as exc:
        _raise_stack_error(exc)

    out: dict[str, int] = {}
    rows = resp[1:] if resp else []

    for row in rows:
        pairs = _row_to_dict(row)
        value = pairs.get(field)
        if value:
            out[str(value)] = int(pairs.get("count", 0))

    return dict(sorted(out.items()))


def _row_to_dict(row) -> dict[str, str]:
    if isinstance(row, dict):
        return {str(key): str(value) for key, value in row.items()}

    if not isinstance(row, (list, tuple)):
        return {}

    out: dict[str, str] = {}
    for index in range(0, len(row), 2):
        if index + 1 < len(row):
            out[str(row[index])] = str(row[index + 1])

    return out


def _build_query(
    *,
    ids: Optional[Iterable[str]] = None,
    q: Optional[str] = None,
    vehicle_types: Optional[Iterable[ParkingVehicleType]] = None,
    categories: Optional[Iterable[ParkingCategory]] = None,
    regulations: Optional[Iterable[ParkingRegulation]] = None,
    datasets: Optional[Iterable[str]] = None,
    min_spaces: int = 0,
    bounds: Optional[tuple[float, float, float, float]] = None,
    geo: Optional[tuple[float, float, float]] = None,
) -> str:
    parts: list[str] = []

    _append_tag_filter(parts, "id", ids)
    _append_tag_filter(parts, "vehicleType", [value.value for value in vehicle_types or []])
    _append_tag_filter(parts, "category", [value.value for value in categories or []])
    _append_tag_filter(parts, "regulation", [value.value for value in regulations or []])
    _append_tag_filter(parts, "sourceDataset", datasets)

    text = _text_query(q)
    if text:
        parts.append(text)

    if min_spaces > 0:
        parts.append(f"@totalSpaces:[{min_spaces} +inf]")

    if bounds is not None:
        min_lat, min_lng, max_lat, max_lng = bounds
        parts.append(f"@latitude:[{min_lat} {max_lat}]")
        parts.append(f"@longitude:[{min_lng} {max_lng}]")

    if geo is not None:
        lng, lat, radius_meters = geo
        parts.append(f"@location:[{lng} {lat} {radius_meters} m]")

    return " ".join(parts) if parts else "*"


def _append_tag_filter(parts: list[str], field: str, values: Optional[Iterable[str]]) -> None:
    raw = [str(value) for value in values or [] if str(value).strip()]
    if not raw:
        return

    joined = "|".join(_escape_tag(value.strip()) for value in raw)
    parts.append(f"@{field}:{{{joined}}}")


def _escape_tag(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else f"\\{char}" for char in value)


def _text_query(q: Optional[str]) -> str:
    normalized = normalize_for_search(q or "")
    terms = _TEXT_TOKEN_RE.findall(normalized)
    if not terms:
        return ""

    return "@searchText:(" + " ".join(f"{term}*" for term in terms) + ")"


def _key_to_id(key: str) -> str:
    key = str(key)
    return key[len(PARKING_KEY_PREFIX):] if key.startswith(PARKING_KEY_PREFIX) else key


def _filter_places(
    places: Iterable[ParkingPlaceOut],
    *,
    ids: Optional[Iterable[str]] = None,
    q: Optional[str] = None,
    vehicle_types: Optional[Iterable[ParkingVehicleType]] = None,
    categories: Optional[Iterable[ParkingCategory]] = None,
    regulations: Optional[Iterable[ParkingRegulation]] = None,
    datasets: Optional[Iterable[str]] = None,
    min_spaces: int = 0,
    bounds: Optional[tuple[float, float, float, float]] = None,
) -> list[ParkingPlaceOut]:
    normalized_q = normalize_for_search(q) if q else None
    dataset_set = {str(dataset) for dataset in datasets or [] if str(dataset).strip()}

    filtered = apply_filters(
        places,
        ids=set(ids) if ids else None,
        normalized_q=normalized_q,
        vehicle_types=set(vehicle_types or []),
        categories=set(categories or []),
        regulations=set(regulations or []),
        min_spaces=min_spaces,
    )

    out: list[ParkingPlaceOut] = []

    for place in filtered:
        if dataset_set and place.sourceDataset not in dataset_set:
            continue

        if bounds is not None:
            min_lat, min_lng, max_lat, max_lng = bounds
            if not (min_lat <= place.latitude <= max_lat and min_lng <= place.longitude <= max_lng):
                continue

        out.append(place)

    return out


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlamb / 2) ** 2
    )

    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
