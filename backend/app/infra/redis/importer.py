"""Importación de datasets GeoJSON municipales a Redis.

Esta capa transforma features heterogéneos del portal municipal al contrato
público `ParkingPlaceOut`, deriva identificadores estables, aplana cada
aparcamiento en un hash Redis y mantiene el índice RediSearch asociado.

El flujo utiliza doble buffer: primero construye una generación de staging
bajo un prefijo temporal y, solo cuando la escritura ha terminado, sustituye
el catálogo activo. De este modo se reduce la ventana en la que una lectura
podría observar un conjunto parcial de datos.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import redis

from ...core.config import (
    CACHE_VERSION_KEY,
    FETCH_PHOTOS,
    PARKING_KEY_PREFIX,
    SEARCH_INDEX_NAME,
    STAGING_INDEX_NAME,
    STAGING_KEY_PREFIX,
)
from ...enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from ...normalization import coerce_line_string, coerce_polygon
from ...schemas import ParkingPlaceOut
from . import photo_resolver
from .search import (
    build_location,
    build_search_text,
    drop_search_index,
    recreate_search_index,
)

logger = logging.getLogger(__name__)


_GEOJSON_TYPE_TO_GEOMETRY: dict[str, ParkingGeometryType] = {
    "Point": ParkingGeometryType.POINT,
    "Polygon": ParkingGeometryType.POLYGON,
    "LineString": ParkingGeometryType.LINE_STRING,
    "MultiPolygon": ParkingGeometryType.POLYGON,
    "MultiLineString": ParkingGeometryType.LINE_STRING,
}


def _coerce_multi_geometry_coords(
    geom_type: str,
    raw_coords: object,
    *,
    feature_id_hint: Optional[str] = None,
) -> object:
    """Colapsa geometrías Multi* a la primera componente válida.

    El contrato expone una única geometría por aparcamiento. Cuando el dataset
    contiene varias componentes, se conserva la primera válida y se registra la
    pérdida para facilitar auditorías posteriores.
    """
    if geom_type == "MultiPolygon":
        if not isinstance(raw_coords, (list, tuple)) or not raw_coords:
            return raw_coords

        for index, polygon in enumerate(raw_coords):
            polygon_clean = coerce_polygon(polygon)
            if polygon_clean:
                _log_multi_dropped(
                    geom_type,
                    total=len(raw_coords),
                    kept_index=index,
                    feature_id_hint=feature_id_hint,
                )
                return [[list(point) for point in ring] for ring in polygon_clean]

        return raw_coords[0]

    if geom_type == "MultiLineString":
        if not isinstance(raw_coords, (list, tuple)) or not raw_coords:
            return raw_coords

        for index, line in enumerate(raw_coords):
            line_clean = coerce_line_string(line)
            if line_clean:
                _log_multi_dropped(
                    geom_type,
                    total=len(raw_coords),
                    kept_index=index,
                    feature_id_hint=feature_id_hint,
                )
                return [list(point) for point in line_clean]

        return raw_coords[0]

    return raw_coords


def _log_multi_dropped(
    geom_type: str,
    *,
    total: int,
    kept_index: int,
    feature_id_hint: Optional[str],
) -> None:
    """Registra descartes de componentes Multi* no triviales."""
    if total <= 1:
        return

    dropped = total - 1
    logger.info(
        "Multi* colapsado a primera componente: type=%s total=%d kept_index=%d "
        "dropped=%d feature=%s",
        geom_type,
        total,
        kept_index,
        dropped,
        feature_id_hint or "<unknown>",
    )


_MSLINK_RE = re.compile(r"mslink=(\d+)")

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


@dataclass(frozen=True)
class SourceProfile:
    """Perfil de normalización asociado a un fichero GeoJSON de origen.

    Agrupa el nombre del fichero, el prefijo de ids corto, los valores por
    defecto para categoría, vehículo y regulación, y el nombre de dataset que
    se expone en el contrato público.
    """

    filename: str
    short_id_prefix: str
    default_category: ParkingCategory
    default_vehicle_type: ParkingVehicleType
    default_regulation: ParkingRegulation
    source_dataset: str
    fallback_name: str = ""


SOURCE_REGISTRY: dict[str, SourceProfile] = {
    "aparcamientos.geojson": SourceProfile(
        filename="aparcamientos.geojson",
        short_id_prefix="aparcamiento",
        default_category=ParkingCategory.PARKING,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.FREE,
        source_dataset="aparcamientos",
        fallback_name="Aparcamiento público",
    ),
    "parkings.geojson": SourceProfile(
        filename="parkings.geojson",
        short_id_prefix="parking",
        default_category=ParkingCategory.PAID_PARKING,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.PAID,
        source_dataset="parkings",
        fallback_name="Parking público",
    ),
    "aparcamientos_en_bateria.geojson": SourceProfile(
        filename="aparcamientos_en_bateria.geojson",
        short_id_prefix="bateria",
        default_category=ParkingCategory.STREET_BATTERY,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.FREE,
        source_dataset="aparcamientos_en_bateria",
        fallback_name="Aparcamiento en batería",
    ),
    "aparcamientos_en_linea.geojson": SourceProfile(
        filename="aparcamientos_en_linea.geojson",
        short_id_prefix="linea",
        default_category=ParkingCategory.STREET_LINE,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.FREE,
        source_dataset="aparcamientos_en_linea",
        fallback_name="Aparcamiento en línea",
    ),
    "zona_azul.geojson": SourceProfile(
        filename="zona_azul.geojson",
        short_id_prefix="azul",
        default_category=ParkingCategory.BLUE_ZONE,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.BLUE_ZONE,
        source_dataset="zona_azul",
        fallback_name="Zona azul",
    ),
    "carga_descarga.geojson": SourceProfile(
        filename="carga_descarga.geojson",
        short_id_prefix="carga",
        default_category=ParkingCategory.LOADING,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.LOADING,
        source_dataset="carga_descarga",
        fallback_name="Carga y descarga",
    ),
    "movilidad_reducida.geojson": SourceProfile(
        filename="movilidad_reducida.geojson",
        short_id_prefix="pmr",
        default_category=ParkingCategory.ACCESSIBLE,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.RESERVED,
        source_dataset="movilidad_reducida",
        fallback_name="Plaza PMR",
    ),
    "parking_bicis.geojson": SourceProfile(
        filename="parking_bicis.geojson",
        short_id_prefix="bici",
        default_category=ParkingCategory.BICYCLE,
        default_vehicle_type=ParkingVehicleType.BIKE,
        default_regulation=ParkingRegulation.RESERVED,
        source_dataset="parking_bicis",
        fallback_name="Aparcamiento de bicis",
    ),
    "parking_motos_areas.geojson": SourceProfile(
        filename="parking_motos_areas.geojson",
        short_id_prefix="moto-area",
        default_category=ParkingCategory.MOTORBIKE,
        default_vehicle_type=ParkingVehicleType.MOTORBIKE,
        default_regulation=ParkingRegulation.RESERVED,
        source_dataset="parking_motos_areas",
        fallback_name="Área de motos",
    ),
    "parking_motos_puntos.geojson": SourceProfile(
        filename="parking_motos_puntos.geojson",
        short_id_prefix="moto-punto",
        default_category=ParkingCategory.MOTORBIKE,
        default_vehicle_type=ParkingVehicleType.MOTORBIKE,
        default_regulation=ParkingRegulation.RESERVED,
        source_dataset="parking_motos_puntos",
        fallback_name="Punto de motos",
    ),
}

_GENERIC_PROFILE = SourceProfile(
    filename="",
    short_id_prefix="aparcamiento",
    default_category=ParkingCategory.PARKING,
    default_vehicle_type=ParkingVehicleType.CAR,
    default_regulation=ParkingRegulation.FREE,
    source_dataset="",
    fallback_name="",
)


def profile_for(filename: str) -> SourceProfile:
    """Devuelve el perfil registrado o uno genérico trazable por nombre de fichero.

    Los ficheros conocidos usan reglas de normalización específicas. Los
    desconocidos caen a un perfil genérico que conserva trazabilidad por stem
    de fichero sin bloquear la importación.
    """
    profile = SOURCE_REGISTRY.get(filename)
    if profile is not None:
        return profile

    stem = filename.rsplit(".", 1)[0] if filename else ""
    return SourceProfile(
        filename=filename,
        short_id_prefix=stem.replace("_", "-") or "aparcamiento",
        default_category=_GENERIC_PROFILE.default_category,
        default_vehicle_type=_GENERIC_PROFILE.default_vehicle_type,
        default_regulation=_GENERIC_PROFILE.default_regulation,
        source_dataset=stem or _GENERIC_PROFILE.source_dataset,
        fallback_name="",
    )


def _first_present(props: dict, *keys: str) -> Any:
    """Devuelve el primer valor presente y no vacío entre varias claves."""
    for key in keys:
        if key not in props:
            continue

        value = props[key]
        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return None


_IMAGE_SUFFIXES: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def _classify_urls(props: dict) -> dict[str, Optional[str]]:
    """Clasifica URLs municipales en foto, ficha de aparcamiento o ficha de vía.

    Las claves explícitas tienen prioridad. Las URLs genéricas se clasifican
    por contenido, usando `urlFicha` como destino de mejor esfuerzo.
    """
    out: dict[str, Optional[str]] = {
        "imageUrl": None,
        "urlFicha": None,
        "urlVia": None,
    }

    explicit_pairs = (
        ("imageUrl", ("imageUrl", "URL_FOTO")),
        ("urlFicha", ("urlFicha", "URL_FICHA")),
        ("urlVia", ("urlVia", "URL_VIA")),
    )

    for dest, keys in explicit_pairs:
        value = _first_present(props, *keys)
        if value is not None:
            out[dest] = str(value)

    raw_url = _first_present(props, "URL", "url")
    if raw_url is not None:
        url = str(raw_url)
        url_lower = url.lower()

        is_image = (
            any(url_lower.endswith(ext) for ext in _IMAGE_SUFFIXES)
            or "/fotosoriginales/" in url_lower
        )

        if is_image:
            out["imageUrl"] = out["imageUrl"] or url
        elif "fichacalle.php" in url_lower:
            out["urlVia"] = out["urlVia"] or url
        else:
            out["urlFicha"] = out["urlFicha"] or url

    return out


def _coords_fingerprint(
    geometry_type: ParkingGeometryType,
    raw_coords: object,
    extra: Optional[tuple[str, ...]] = None,
) -> str:
    """Genera un fingerprint determinista para features sin identificador estable."""
    payload = json.dumps(
        [geometry_type.value, raw_coords, list(extra or ())],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


_MUNICIPAL_STABLE_KEYS: tuple[str, ...] = (
    "id", "ID",
    "OBJECTID", "objectid",
    "MSLINK", "mslink",
    "CODIGO", "codigo",
)

_FINGERPRINT_PROPERTY_KEYS: tuple[str, ...] = (
    "TIPO", "PLAZAS", "NOMBRE_VIA", "NOMBREVIA",
    "TIPO_VIA", "TIPOVIA", "CODIGO_VIA", "CODIGOVIA",
)


def _namespace_for(source: Optional[SourceProfile]) -> str:
    """Obtiene el namespace de ids asociado al dataset de origen."""
    if source is None:
        return ""

    return source.source_dataset or source.short_id_prefix


def derive_stable_id(
    properties: dict,
    *,
    source: Optional[SourceProfile] = None,
    geometry_type: Optional[ParkingGeometryType] = None,
    raw_coords: object = None,
) -> Optional[str]:
    """Deriva un identificador estable y namespaced para un feature.

    La prioridad es `mslink`, después las claves municipales explícitas y, como
    último recurso, un hash de geometría y propiedades relevantes. El namespace
    evita colisiones entre datasets distintos que reutilizan identificadores
    locales.
    """
    namespace = _namespace_for(source)

    for key in ("URL", "url", "URL_FICHA", "urlFicha"):
        url = properties.get(key)
        if not url:
            continue

        match = _MSLINK_RE.search(str(url))
        if match:
            token = match.group(1)
            return f"{namespace}:{token}" if namespace else None

    for prop_key in _MUNICIPAL_STABLE_KEYS:
        explicit = properties.get(prop_key)
        if explicit in (None, ""):
            continue

        stripped = str(explicit).strip()
        if not stripped:
            continue

        return f"{namespace}:{stripped}" if namespace else stripped

    if source is None or geometry_type is None or raw_coords is None:
        return None

    extra_parts: list[str] = []
    for prop_key in _FINGERPRINT_PROPERTY_KEYS:
        value = properties.get(prop_key)
        if value not in (None, ""):
            extra_parts.append(f"{prop_key}={value}")

    fingerprint = _coords_fingerprint(geometry_type, raw_coords, tuple(extra_parts))
    return f"{namespace}:{fingerprint}"


def _polygon_centroid(ring: list[tuple[float, float]]) -> Optional[tuple[float, float]]:
    """Calcula el centroide de un anillo usando la fórmula de Shoelace.

    Si el anillo es degenerado, se usa el promedio aritmético para conservar el
    feature con un punto representativo razonable.
    """
    points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not points:
        return None

    if len(points) < 3:
        lon = sum(point[0] for point in points) / len(points)
        lat = sum(point[1] for point in points) / len(points)
        return (lon, lat)

    area_x2 = 0.0
    cx = 0.0
    cy = 0.0
    total_points = len(points)

    for index in range(total_points):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % total_points]
        cross = x0 * y1 - x1 * y0
        area_x2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    if area_x2 == 0:
        lon = sum(point[0] for point in points) / total_points
        lat = sum(point[1] for point in points) / total_points
        return (lon, lat)

    factor = 1.0 / (3.0 * area_x2)
    return (cx * factor, cy * factor)


def representative_point(
    geometry_type: ParkingGeometryType,
    raw_coords: object,
) -> Optional[tuple[float, float]]:
    """Obtiene un punto `(lon, lat)` válido para indexación geoespacial."""
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

        return _polygon_centroid(polygon[0])

    if geometry_type is ParkingGeometryType.LINE_STRING:
        line = coerce_line_string(raw_coords)
        if not line:
            return None

        return line[len(line) // 2]

    return None


def feature_to_place(
    feature: dict,
    *,
    source: Optional[SourceProfile] = None,
) -> Optional[ParkingPlaceOut]:
    """Convierte un feature GeoJSON al contrato `ParkingPlaceOut`.

    El proceso valida la geometría, colapsa componentes Multi* cuando existen,
    calcula un punto representativo para indexación geoespacial, clasifica las
    URLs municipales y completa los valores faltantes con el perfil de origen.
    Devuelve `None` si el feature no puede normalizarse con garantías mínimas.
    """
    geometry = feature.get("geometry") or {}
    properties = feature.get("properties") or {}

    raw_geom_type = geometry.get("type")
    geom_type = _GEOJSON_TYPE_TO_GEOMETRY.get(raw_geom_type)
    if geom_type is None:
        return None

    raw_coords = geometry.get("coordinates")
    if raw_geom_type in ("MultiPolygon", "MultiLineString"):
        hint_dataset = source.source_dataset if source else "<no-source>"
        hint_token = (
            properties.get("MSLINK")
            or properties.get("mslink")
            or properties.get("ID")
            or properties.get("id")
            or properties.get("OBJECTID")
            or "<no-id>"
        )
        raw_coords = _coerce_multi_geometry_coords(
            raw_geom_type,
            raw_coords,
            feature_id_hint=f"{hint_dataset}:{hint_token}",
        )

    point = representative_point(geom_type, raw_coords)
    if point is None:
        return None

    lon, lat = point

    parking_id = derive_stable_id(
        properties,
        source=source,
        geometry_type=geom_type,
        raw_coords=raw_coords,
    )
    if parking_id is None:
        return None

    explicit_category = properties.get("category")
    category = explicit_category if explicit_category is not None else (
        source.default_category if source is not None else None
    )

    explicit_vehicle = properties.get("vehicleType")
    vehicle_type = explicit_vehicle if explicit_vehicle is not None else (
        source.default_vehicle_type if source is not None else None
    )

    explicit_regulation = properties.get("regulation")
    regulation = explicit_regulation if explicit_regulation is not None else (
        source.default_regulation if source is not None else None
    )

    raw_name = _first_present(properties, "name", "NOMBRE", "DENOMINACI")
    if raw_name is None:
        raw_name = _build_fallback_name(properties, source)

    name = "" if raw_name is None else str(raw_name)

    total_spaces = _first_present(
        properties, "totalSpaces", "TOTAL_SPACES", "PLAZAS"
    )
    street_name = _first_present(
        properties, "streetName", "NOMBREVIA", "NOMBRE_VIA", "DIRECCION"
    )
    street_type = _first_present(properties, "streetType", "TIPOVIA", "TIPO_VIA")
    district = _first_present(properties, "district", "DISTRITO", "NUCLEO")
    neighborhood = _first_present(properties, "neighborhood", "BARRIO")
    management = _first_present(properties, "management", "GESTION")

    explicit_source_dataset = _first_present(properties, "sourceDataset")
    source_dataset = explicit_source_dataset if explicit_source_dataset is not None else (
        source.source_dataset if source is not None and source.source_dataset else None
    )

    urls = _classify_urls(properties)

    return ParkingPlaceOut(
        id=parking_id,
        name=name,
        category=category,
        vehicleType=vehicle_type,
        regulation=regulation,
        geometryType=geom_type,
        latitude=lat,
        longitude=lon,
        coordinates=raw_coords,
        totalSpaces=total_spaces,
        streetName=street_name,
        streetType=street_type,
        district=district,
        neighborhood=neighborhood,
        sourceDataset=source_dataset,
        imageUrl=urls["imageUrl"],
        urlFicha=urls["urlFicha"],
        urlVia=urls["urlVia"],
        management=management,
    )


def _build_fallback_name(props: dict, source: Optional[SourceProfile]) -> Optional[str]:
    """Construye un nombre legible cuando el feature no aporta uno explícito."""
    street_type = _first_present(props, "streetType", "TIPOVIA", "TIPO_VIA")
    street_name = _first_present(props, "streetName", "NOMBREVIA", "NOMBRE_VIA")

    if street_name:
        if street_type:
            return f"{street_type} {street_name}".strip()

        return str(street_name)

    if source is not None and source.fallback_name:
        return source.fallback_name

    return None


def place_to_redis_mapping(place: ParkingPlaceOut) -> dict[str, str]:
    """Aplana un aparcamiento a un mapping apto para `HSET`.

    Redis almacena los campos como cadenas. Los valores ausentes se omiten para
    que la reconstrucción conserve `null` en el contrato público. Además, los
    campos derivados `location` y `searchText` se materializan aquí para que el
    índice RediSearch pueda consultar sin recomputar el contrato completo.
    """
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

    out["location"] = build_location(place)
    out["searchText"] = build_search_text(place)

    return out


def place_from_redis_hash(data: dict[str, str]) -> ParkingPlaceOut:
    """Reconstruye un aparcamiento desde un hash Redis.

    Es la operación inversa de `place_to_redis_mapping`: recupera los tipos
    compuestos que Redis almacena serializados y delega la validación final en
    `ParkingPlaceOut`.
    """
    payload: dict[str, Any] = dict(data)

    if "coordinates" in payload:
        try:
            payload["coordinates"] = json.loads(payload["coordinates"])
        except (TypeError, ValueError):
            payload["coordinates"] = None

    return ParkingPlaceOut(**payload)


def run_import_sources(
    sources: Iterable[tuple[Iterable[dict], Optional[SourceProfile]]],
    rdb: redis.Redis,
) -> dict[str, Any]:
    """Importa varios conjuntos de features con su perfil de origen.

    Esta función es la entrada pública para importar un lote ya agrupado por
    dataset. Conserva la asociación entre features y perfil para que la
    normalización y la generación de ids puedan aplicar reglas específicas por
    origen.
    """
    paired: list[tuple[dict, Optional[SourceProfile]]] = []

    for features, profile in sources:
        for feature in features:
            paired.append((feature, profile))

    return _run_import_paired(iter(paired), rdb)


def _run_import_paired(
    features_with_profile: Iterator[tuple[dict, Optional[SourceProfile]]],
    rdb: redis.Redis,
) -> dict[str, Any]:
    """Ejecuta la importación completa con staging, swap e invalidación de caché.

    Normaliza primero todas las features, después resuelve duplicados de ids,
    opcionalmente completa fotos, reconstruye el índice de staging y, por
    último, intercambia la generación activa con un renombrado controlado.
    """
    pairs = list(features_with_profile)

    imported = 0
    skipped = 0
    base_id_counts: dict[str, int] = {}
    valid_places: list[ParkingPlaceOut] = []
    per_source: dict[str, dict[str, int]] = {}

    for feature, profile in pairs:
        bucket_key = profile.source_dataset if profile is not None else ""
        bucket = per_source.setdefault(bucket_key, {"imported": 0, "skipped": 0})

        place = feature_to_place(feature, source=profile)
        if place is None:
            skipped += 1
            bucket["skipped"] += 1
            continue

        valid_places.append(place)
        base_id_counts[place.id] = base_id_counts.get(place.id, 0) + 1
        imported += 1
        bucket["imported"] += 1

    disambiguated = 0
    if any(count > 1 for count in base_id_counts.values()):
        occurrences: dict[str, int] = {}
        unique_places: list[ParkingPlaceOut] = []

        for place in valid_places:
            if base_id_counts[place.id] == 1:
                unique_places.append(place)
                continue

            occurrences[place.id] = occurrences.get(place.id, 0) + 1
            occurrence = occurrences[place.id]

            if occurrence == 1:
                unique_places.append(place)
                continue

            disambiguated += 1
            unique_places.append(place.model_copy(update={"id": f"{place.id}:{occurrence}"}))

        valid_places = unique_places

    final_ids = [place.id for place in valid_places]
    if len(final_ids) != len(set(final_ids)):
        raise ValueError("ids duplicados tras desambiguar la importación")

    photos_resolved = 0
    if FETCH_PHOTOS:
        ficha_tasks: list[tuple[str, str]] = []

        for place in valid_places:
            if place.imageUrl:
                continue

            ficha = place.urlFicha or place.urlVia
            if ficha:
                ficha_tasks.append((place.id, ficha))

        if ficha_tasks:
            try:
                resolved_urls = asyncio.run(
                    photo_resolver.resolve_many(ficha_tasks, rdb)
                )
            except Exception:
                logger.exception("Resolución de fotos falló; continuando sin fotos")
                resolved_urls = {}

            if resolved_urls:
                updated: list[ParkingPlaceOut] = []

                for place in valid_places:
                    new_url = resolved_urls.get(place.id)
                    if new_url and not place.imageUrl:
                        updated.append(place.model_copy(update={"imageUrl": new_url}))
                        photos_resolved += 1
                    else:
                        updated.append(place)

                valid_places = updated

    drop_search_index(rdb, name=STAGING_INDEX_NAME)

    stale_staging_keys = list(rdb.scan_iter(match=f"{STAGING_KEY_PREFIX}*"))
    if stale_staging_keys:
        prep = rdb.pipeline()
        _unlink_or_delete(prep, *stale_staging_keys)
        prep.execute()

    recreate_search_index(
        rdb,
        name=STAGING_INDEX_NAME,
        key_prefix=STAGING_KEY_PREFIX,
    )

    write_pipe = rdb.pipeline()
    for place in valid_places:
        write_pipe.hset(
            f"{STAGING_KEY_PREFIX}{place.id}",
            mapping=place_to_redis_mapping(place),
        )
    write_pipe.execute()

    old_active_keys = list(rdb.scan_iter(match=f"{PARKING_KEY_PREFIX}*"))

    drop_search_index(rdb, name=SEARCH_INDEX_NAME)

    if old_active_keys:
        cleanup_active = rdb.pipeline()
        _unlink_or_delete(cleanup_active, *old_active_keys)
        cleanup_active.execute()

    rename_pipe = rdb.pipeline()
    for place in valid_places:
        _rename(
            rename_pipe,
            f"{STAGING_KEY_PREFIX}{place.id}",
            f"{PARKING_KEY_PREFIX}{place.id}",
        )
    rename_pipe.execute()

    drop_search_index(rdb, name=STAGING_INDEX_NAME)
    recreate_search_index(rdb)

    try:
        new_version = int(rdb.incr(CACHE_VERSION_KEY))
    except redis.ConnectionError:
        logger.warning("No se pudo incrementar %s al reimportar", CACHE_VERSION_KEY)
        new_version = 0

    return {
        "status": "ok",
        "imported": imported,
        "skipped": skipped,
        "search_index": SEARCH_INDEX_NAME,
        "ids_disambiguated": disambiguated,
        "photos_resolved": photos_resolved,
        "cache_version": new_version,
        "sources": [
            {
                "sourceDataset": name or None,
                "imported": stats["imported"],
                "skipped": stats["skipped"],
            }
            for name, stats in sorted(per_source.items())
        ],
    }


def _unlink_or_delete(pipe, *keys: str) -> None:
    """Encola borrado no bloqueante y degrada a `DELETE` si no existe `UNLINK`.

    Se usa para limpiar generaciones antiguas sin bloquear el servidor cuando
    el cliente Redis soporta la operación moderna.
    """
    if not keys:
        return

    if hasattr(pipe, "unlink"):
        pipe.unlink(*keys)
    else:
        pipe.delete(*keys)


def _rename(pipe, src: str, dst: str) -> None:
    """Encola un renombrado compatible con clientes Redis de test.

    Algunos dobles de prueba exponen solo la API mínima. Esta envoltura mantiene
    el contrato de producción sin introducir dependencias al backend real.
    """
    if hasattr(pipe, "rename"):
        pipe.rename(src, dst)
    else:
        pipe.execute_command("RENAME", src, dst)


def discover_geojson_files(data_dir: Path) -> list[Path]:
    """Lista ficheros GeoJSON importables en orden estable.

    El orden determinista evita cambios espurios en importaciones y facilita la
    comparación de resultados entre ejecuciones.
    """
    if not data_dir.exists() or not data_dir.is_dir():
        return []

    return sorted(path for path in data_dir.glob("*.geojson") if path.is_file())


def _load_features(path: Path) -> list[dict]:
    """Lee las features de un GeoJSON, o una lista vacía si no existen.

    El importador solo necesita la colección `features`; el resto del documento
    se ignora porque no forma parte del contrato público.
    """
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    if not isinstance(data, dict):
        return []

    features = data.get("features")
    return list(features) if isinstance(features, list) else []


def run_import_dir(data_dir: Path, rdb: redis.Redis) -> dict[str, Any]:
    """Importa todos los GeoJSON de un directorio.

    Los ficheros ilegibles se registran y no interrumpen el resto de la
    importación. Los errores de Redis se propagan a la capa HTTP porque la
    persistencia es una dependencia operativa y no un detalle local de parsing.
    """
    files = discover_geojson_files(data_dir)
    if not files:
        logger.warning("No se encontraron ficheros *.geojson en %s", data_dir)

    sources: list[tuple[list[dict], SourceProfile]] = []
    skipped_files: list[dict[str, str]] = []

    for path in files:
        profile = profile_for(path.name)

        try:
            features = _load_features(path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("No se pudo leer %s: %s", path.name, exc)
            skipped_files.append({"filename": path.name, "error": str(exc)})
            continue

        sources.append((features, profile))

    summary = run_import_sources(sources, rdb)
    summary["files_processed"] = len(sources)
    summary["files_skipped"] = skipped_files
    return summary
