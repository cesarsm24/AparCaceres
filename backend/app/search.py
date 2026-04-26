"""Capa de búsqueda del catálogo de aparcamientos.

Producción usa Redis Stack / RediSearch sobre los hashes `parking:{id}`.
Los tests usan un fallback en memoria contra `FakeRedis`, para no depender de
un servidor Redis Stack real en CI.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import redis
from redis.exceptions import ResponseError

from .config import (
    PARKING_KEY_PREFIX,
    SEARCH_INDEX_NAME,
)
from .enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from .filters import apply_filters, normalize_for_search
from .schemas import ParkingFacetsOut, ParkingPlaceNearbyOut, ParkingPlaceOut

_EARTH_RADIUS_M = 6_371_000.0
_TEXT_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class SearchIndexError(RuntimeError):
    """Error de configuración de RediSearch."""


@dataclass(frozen=True)
class ParkingSearchResult:
    items: list[ParkingPlaceOut]
    total: int


@dataclass(frozen=True)
class ParkingNearbySearchResult:
    items: list[ParkingPlaceNearbyOut]
    total: int


def build_search_text(place: ParkingPlaceOut) -> str:
    """Texto normalizado indexable para búsqueda libre."""
    values = [
        place.name,
        place.streetName,
        place.streetType,
        place.district,
        place.neighborhood,
        place.sourceDataset,
        place.category.value,
        place.vehicleType.value,
        place.regulation.value,
    ]
    return normalize_for_search(" ".join(v for v in values if v))


def build_location(place: ParkingPlaceOut) -> str:
    """Formato GEO de RediSearch: `lon,lat`."""
    return f"{place.longitude},{place.latitude}"


def recreate_search_index(rdb: redis.Redis) -> None:
    """Recrea `idx:parkings_search` de forma idempotente.

    No usa `DD`: el importador borra los hashes explícitamente y luego vuelve a
    crearlos, así evitamos que `FT.DROPINDEX` borre datos por accidente.
    """
    if not hasattr(rdb, "execute_command"):
        return
    try:
        rdb.execute_command("FT.DROPINDEX", SEARCH_INDEX_NAME)
    except ResponseError as exc:
        if not _is_unknown_index(exc):
            _raise_stack_error(exc)
    _create_search_index(rdb)


def ensure_search_index(rdb: redis.Redis) -> None:
    """Crea el índice RediSearch si no existe."""
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
    """Busca aparcamientos con filtros indexados."""
    if not _has_redisearch(rdb):
        return _search_parkings_fake(
            rdb,
            ids=ids,
            q=q,
            vehicle_types=vehicle_types,
            categories=categories,
            regulations=regulations,
            datasets=datasets,
            min_spaces=min_spaces,
            offset=offset,
            limit=limit,
        )

    query = _build_query(
        ids=ids,
        q=q,
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
    )
    total, parking_ids = _ft_search_ids(rdb, query, offset=offset, limit=limit)
    return ParkingSearchResult(items=_load_places(rdb, parking_ids), total=total)


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
    """Busca por radio y ordena por distancia ascendente."""
    if not _has_redisearch(rdb):
        return _search_nearby_fake(
            rdb,
            lat=lat,
            lng=lng,
            radius_meters=radius_meters,
            ids=ids,
            q=q,
            vehicle_types=vehicle_types,
            categories=categories,
            regulations=regulations,
            datasets=datasets,
            min_spaces=min_spaces,
            offset=offset,
            limit=limit,
        )

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
    total, rows = _ft_nearby_rows(
        rdb,
        query=query,
        lng=lng,
        lat=lat,
        offset=offset,
        limit=limit,
    )
    places_by_id = {place.id: place for place in _load_places(rdb, [row[0] for row in rows])}
    nearby: list[ParkingPlaceNearbyOut] = []
    for parking_id, distance in rows:
        place = places_by_id.get(parking_id)
        if place is None:
            continue
        nearby.append(
            ParkingPlaceNearbyOut(
                **place.model_dump(),
                distanceMeters=distance,
            )
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
    """Busca por viewport rectangular usando campos numéricos indexados."""
    if not _has_redisearch(rdb):
        return _search_parkings_fake(
            rdb,
            vehicle_types=vehicle_types,
            categories=categories,
            regulations=regulations,
            datasets=datasets,
            min_spaces=min_spaces,
            bounds=(min_lat, min_lng, max_lat, max_lng),
            offset=offset,
            limit=limit,
        )

    query = _build_query(
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
        bounds=(min_lat, min_lng, max_lat, max_lng),
    )
    total, parking_ids = _ft_search_ids(rdb, query, offset=offset, limit=limit)
    return ParkingSearchResult(items=_load_places(rdb, parking_ids), total=total)


def get_facets(rdb: redis.Redis) -> ParkingFacetsOut:
    """Conteos por dimensión, vía RediSearch en producción."""
    if not _has_redisearch(rdb):
        return _facets_fake(rdb)

    total, _ = _ft_search_ids(rdb, "*", offset=0, limit=0)
    return ParkingFacetsOut(
        total=total,
        categories=_aggregate_tag_counts(rdb, "category"),
        vehicleTypes=_aggregate_tag_counts(rdb, "vehicleType"),
        regulations=_aggregate_tag_counts(rdb, "regulation"),
        datasets=_aggregate_tag_counts(rdb, "sourceDataset"),
    )


def _create_search_index(rdb: redis.Redis) -> None:
    try:
        rdb.execute_command(
            "FT.CREATE",
            SEARCH_INDEX_NAME,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            PARKING_KEY_PREFIX,
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
            "geometryType",
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


def _has_redisearch(rdb: redis.Redis) -> bool:
    return hasattr(rdb, "execute_command")


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
    return total, [_key_to_id(k) for k in resp[1:]]


def _ft_nearby_rows(
    rdb: redis.Redis,
    *,
    query: str,
    lng: float,
    lat: float,
    offset: int,
    limit: int,
) -> tuple[int, list[tuple[str, float]]]:
    """Nearby ordenado en Redis con `geodistance(...)`.

    RediSearch permite cargar el campo GEO, aplicar `geodistance` y ordenar por
    esa propiedad calculada en el pipeline de `FT.AGGREGATE`. Así no traemos
    una ventana arbitraria a Python ni corremos el riesgo de perder los puntos
    realmente más cercanos cuando el índice crezca.
    """
    ensure_search_index(rdb)
    sort_window = max(offset + limit, limit)
    try:
        resp = rdb.execute_command(
            "FT.AGGREGATE",
            SEARCH_INDEX_NAME,
            query,
            "LOAD",
            "2",
            "@id",
            "@location",
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
    rows: list[tuple[str, float]] = []
    for row in resp[1:]:
        values = _row_to_dict(row)
        parking_id = values.get("id")
        if not parking_id:
            continue
        try:
            distance = float(values.get("distance", 0))
        except (TypeError, ValueError):
            distance = 0.0
        rows.append((parking_id, distance))
    return int(resp[0]), rows


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
        return {str(k): str(v) for k, v in row.items()}
    if not isinstance(row, (list, tuple)):
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(row), 2):
        if i + 1 < len(row):
            out[str(row[i])] = str(row[i + 1])
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
    _append_tag_filter(parts, "vehicleType", [v.value for v in vehicle_types or []])
    _append_tag_filter(parts, "category", [c.value for c in categories or []])
    _append_tag_filter(parts, "regulation", [r.value for r in regulations or []])
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
    raw = [str(v) for v in values or [] if str(v).strip()]
    if not raw:
        return
    joined = "|".join(_escape_tag(v.strip()) for v in raw)
    parts.append(f"@{field}:{{{joined}}}")


def _escape_tag(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else f"\\{ch}" for ch in value)


def _text_query(q: Optional[str]) -> str:
    normalized = normalize_for_search(q or "")
    terms = _TEXT_TOKEN_RE.findall(normalized)
    if not terms:
        return ""
    return "@searchText:(" + " ".join(f"{term}*" for term in terms) + ")"


def _key_to_id(key: str) -> str:
    key = str(key)
    return key[len(PARKING_KEY_PREFIX):] if key.startswith(PARKING_KEY_PREFIX) else key


def _load_places(rdb: redis.Redis, parking_ids: list[str]) -> list[ParkingPlaceOut]:
    if not parking_ids:
        return []
    from .importer import place_from_redis_hash

    pipe = rdb.pipeline()
    for pid in parking_ids:
        pipe.hgetall(f"{PARKING_KEY_PREFIX}{pid}")
    hashes = pipe.execute()
    return [place_from_redis_hash(data) for data in hashes if data]


def _all_places_fake(rdb) -> list[ParkingPlaceOut]:
    from .importer import place_from_redis_hash

    places: list[ParkingPlaceOut] = []
    if hasattr(rdb, "hashes"):
        keys = [k for k in rdb.hashes if k.startswith(PARKING_KEY_PREFIX)]
    else:
        keys = list(rdb.scan_iter(match=f"{PARKING_KEY_PREFIX}*"))
    for key in keys:
        data = rdb.hgetall(key)
        if data:
            places.append(place_from_redis_hash(data))
    return places


def _search_parkings_fake(
    rdb,
    *,
    ids: Optional[Iterable[str]] = None,
    q: Optional[str] = None,
    vehicle_types: Optional[Iterable[ParkingVehicleType]] = None,
    categories: Optional[Iterable[ParkingCategory]] = None,
    regulations: Optional[Iterable[ParkingRegulation]] = None,
    datasets: Optional[Iterable[str]] = None,
    min_spaces: int = 0,
    bounds: Optional[tuple[float, float, float, float]] = None,
    offset: int = 0,
    limit: int = 100,
) -> ParkingSearchResult:
    places = _all_places_fake(rdb)
    filtered = _filter_places(
        places,
        ids=ids,
        q=q,
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
        bounds=bounds,
    )
    return ParkingSearchResult(
        items=filtered[offset : offset + limit],
        total=len(filtered),
    )


def _search_nearby_fake(
    rdb,
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
    candidates = []
    for place in _all_places_fake(rdb):
        distance = _haversine_m(lat, lng, place.latitude, place.longitude)
        if distance <= radius_meters:
            candidates.append((place, distance))

    filtered = _filter_places(
        [place for place, _ in candidates],
        ids=ids,
        q=q,
        vehicle_types=vehicle_types,
        categories=categories,
        regulations=regulations,
        datasets=datasets,
        min_spaces=min_spaces,
    )
    distance_by_id = {place.id: distance for place, distance in candidates}
    out = [
        ParkingPlaceNearbyOut(
            **place.model_dump(),
            distanceMeters=distance_by_id[place.id],
        )
        for place in filtered
    ]
    out.sort(key=lambda p: p.distanceMeters)
    return ParkingNearbySearchResult(
        items=out[offset : offset + limit],
        total=len(out),
    )


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
    dataset_set = {str(d) for d in datasets or [] if str(d).strip()}
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


def _facets_fake(rdb) -> ParkingFacetsOut:
    places = _all_places_fake(rdb)
    return ParkingFacetsOut(
        total=len(places),
        categories=_count_field(places, "category"),
        vehicleTypes=_count_field(places, "vehicleType"),
        regulations=_count_field(places, "regulation"),
        datasets=_count_field(places, "sourceDataset"),
    )


def _count_field(places: Iterable[ParkingPlaceOut], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for place in places:
        value = getattr(place, field)
        if value is None:
            continue
        if isinstance(value, (ParkingCategory, ParkingVehicleType, ParkingRegulation, ParkingGeometryType)):
            key = value.value
        else:
            key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlamb / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
