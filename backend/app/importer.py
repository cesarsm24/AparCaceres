"""Importador del dataset municipal al contrato móvil + Redis.

Pipeline:

  data/*.geojson  ->  feature_to_place(feat, source=profile)  ->  ParkingPlaceOut
                                                                     |
                                                            place_to_redis_mapping
                                                                     |
                                            HSET parking:{id} + GEOADD geo:parkings

El paso intermedio normaliza features muy heterogéneos (Open Data Cáceres
publica cada capa con su propio shape de propiedades, y algunos ficheros
llegan con `properties: {}`). Los `SourceProfile` proporcionan los defaults
de negocio (category, vehicleType, regulation) que no se pueden inferir del
feature suelto, y un prefijo de id que permite generar fallbacks deterministas
cuando no hay `mslink` ni id explícito.

`feature_to_place(feat)` (sin source) sigue funcionando para tests y para los
casos sintéticos: usa los defaults del enum y exige `mslink`/`id` explícito.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import redis

from .config import CACHE_NEARBY_PREFIX, GEO_KEY, PARKING_KEY_PREFIX
from .enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
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
# SourceProfile: contexto por fichero de origen
# ============================================================

@dataclass(frozen=True)
class SourceProfile:
    """Metadatos por fichero de origen.

    El registry (`SOURCE_REGISTRY`) mapea filename -> profile y se usa para:
    - inferir `category` / `vehicleType` / `regulation` cuando el feature no
      los aporta (p. ej. `parkings_en_superficie.geojson` con `properties: {}`),
    - etiquetar `sourceDataset` con el nombre lógico del dataset,
    - generar un id determinista cuando no hay `mslink` ni id explícito
      (`{short_id_prefix}-{sha1_de_filename_y_coords}`).
    """

    filename: str
    short_id_prefix: str
    default_category: ParkingCategory
    default_vehicle_type: ParkingVehicleType
    default_regulation: ParkingRegulation
    source_dataset: str
    fallback_name: str = ""  # name a usar si el feature no trae ninguno


# Registry: filename -> SourceProfile. Si llega un fichero que no está aquí
# se usa `_GENERIC_PROFILE` (defaults seguros: parking / car / free).
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
        # `parkings.geojson` lista los parkings públicos de pago (Obispo Galarza,
        # Cánovas, ...): los marcamos como `paid_parking` + `regulation=paid`.
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
    "parkings_en_superficie.geojson": SourceProfile(
        # 15.000+ LineStrings con `properties: {}`. Sin TIPO no podemos saber si
        # son línea o batería; el default seguro es `parking` y free.
        filename="parkings_en_superficie.geojson",
        short_id_prefix="superficie",
        default_category=ParkingCategory.PARKING,
        default_vehicle_type=ParkingVehicleType.CAR,
        default_regulation=ParkingRegulation.FREE,
        source_dataset="parkings_en_superficie",
        fallback_name="Aparcamiento en superficie",
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
        # Cuidado: el TIPO interno es heterogéneo ("ZONA AZUL", "EN BATERIA"...);
        # el filename es la pista verdadera para clasificar el feature.
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

# Profile para ficheros que no estén en el registry — defaults conservadores.
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
    """Devuelve el profile registrado o uno genérico con `source_dataset = stem`."""
    profile = SOURCE_REGISTRY.get(filename)
    if profile is not None:
        return profile
    # Para ficheros desconocidos, etiquetamos `sourceDataset` con su stem para
    # que sea trazable de dónde vino cada feature.
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


# ============================================================
# Lectura tolerante de propiedades
# ============================================================

def _first_present(props: dict, *keys: str) -> Any:
    """Devuelve el primer valor no-vacío entre las claves dadas.

    "Vacío" = `None`, cadena vacía, o cadena solo de whitespace. Otros valores
    falsy (0, False) se respetan: aunque no aparecen en el dataset real, no
    queremos comernos un `0` por accidente.
    """
    for k in keys:
        if k in props:
            v = props[k]
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return v
    return None


# Suffixes de imagen reconocibles (case-insensitive). Si la URL termina en uno
# de estos o contiene `/fotosOriginales/`, la clasificamos como `imageUrl`.
_IMAGE_SUFFIXES: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def _classify_urls(props: dict) -> dict[str, Optional[str]]:
    """Reparte URLs heterogéneas a `imageUrl` / `urlFicha` / `urlVia`.

    Reglas:
    1. Si llegan claves explícitas en su forma moderna (`imageUrl`, `urlFicha`,
       `urlVia`) o en su forma municipal (`URL_FOTO`, `URL_FICHA`, `URL_VIA`),
       cada una se mapea a su destino correspondiente.
    2. La clave genérica `URL` / `url` se clasifica por contenido:
       - `*.jpg/.png/.gif/.webp` o `/fotosOriginales/` -> `imageUrl`,
       - `fichacalle.php` -> `urlVia` (ficha de la calle, no del aparcamiento),
       - `fichatoponimia.php` o `mslink=` -> `urlFicha`,
       - resto -> `urlFicha` como mejor esfuerzo.

    Las claves explícitas tienen prioridad sobre la heurística.
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
            # `fichatoponimia.php`, `mslink=`, o desconocido: lo dejamos en urlFicha.
            out["urlFicha"] = out["urlFicha"] or url

    return out


# ============================================================
# Derivación de id y punto representativo
# ============================================================

def _coords_fingerprint(geometry_type: ParkingGeometryType, raw_coords: object) -> str:
    """Hash sha1 truncado a 12 hex chars de (geometryType, coords).

    Determinista: el mismo feature en el mismo fichero produce siempre el mismo
    id, así que reimportar no genera duplicados aunque no haya mslink.
    Usamos `sort_keys=True` y `separators` compactos para que pequeñas
    diferencias de formato JSON no rompan la estabilidad.
    """
    payload = json.dumps(
        [geometry_type.value, raw_coords],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def derive_stable_id(
    properties: dict,
    *,
    source: Optional[SourceProfile] = None,
    geometry_type: Optional[ParkingGeometryType] = None,
    raw_coords: object = None,
) -> Optional[str]:
    """Extrae un id estable para el feature.

    Prioridad:
    1. `mslink=NNNN` extraído de cualquier URL del feature (formato canónico
       histórico: `aparcamiento-{mslink}`). Se respeta para mantener ids
       compatibles entre reimports.
    2. Campo `id` / `ID` explícito si llega del dataset.
    3. Fallback determinista: `{source.short_id_prefix}-{sha1_de_coords}`.
       Requiere `source`, `geometry_type` y `raw_coords`. Sin source no hay
       fallback (compat: tests sintéticos sin source siguen exigiendo
       mslink/id explícito).

    Devuelve `None` si no se puede derivar — el feature se descartará.
    """
    # 1) mslink de cualquier URL conocida.
    for key in ("URL", "url", "URL_FICHA", "urlFicha"):
        url = properties.get(key)
        if url:
            match = _MSLINK_RE.search(str(url))
            if match:
                return f"aparcamiento-{match.group(1)}"

    # 2) id explícito.
    explicit = properties.get("id") or properties.get("ID")
    if explicit not in (None, ""):
        stripped = str(explicit).strip()
        if stripped:
            return stripped

    # 3) fallback determinista (solo cuando viene un source).
    if source is not None and geometry_type is not None and raw_coords is not None:
        return f"{source.short_id_prefix}-{_coords_fingerprint(geometry_type, raw_coords)}"

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

def feature_to_place(
    feature: dict,
    *,
    source: Optional[SourceProfile] = None,
) -> Optional[ParkingPlaceOut]:
    """Convierte un Feature GeoJSON al contrato móvil.

    `source` aporta defaults de negocio cuando el feature carece de ellos
    (típico de los ficheros municipales por capa: la categoría es implícita
    al fichero). Los valores explícitos en `properties` siempre ganan al
    profile, y el profile gana al default del enum.

    Devuelve `None` cuando el feature no se puede importar (geometría no
    soportada, sin id derivable, o coordenadas degeneradas).
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

    parking_id = derive_stable_id(
        properties,
        source=source,
        geometry_type=geom_type,
        raw_coords=raw_coords,
    )
    if parking_id is None:
        return None

    # ---------- Defaults: explicit prop > profile > enum default ----------
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

    # ---------- Name fallback chain ----------
    # Orden: name (camelCase moderno) > NOMBRE > DENOMINACI (truncado en
    # shapefile) > nombre vía + tipo (mejor que vacío para superficie).
    raw_name = _first_present(properties, "name", "NOMBRE", "DENOMINACI")
    if raw_name is None:
        raw_name = _build_fallback_name(properties, source)
    name = "" if raw_name is None else str(raw_name)

    # ---------- Otros campos opcionales ----------
    total_spaces = _first_present(
        properties, "totalSpaces", "TOTAL_SPACES", "PLAZAS"
    )
    street_name = _first_present(
        properties, "streetName", "NOMBREVIA", "NOMBRE_VIA", "DIRECCION"
    )
    street_type = _first_present(properties, "streetType", "TIPOVIA", "TIPO_VIA")
    # Preferimos DISTRITO (subzona: OESTE, CENTRO) sobre NUCLEO (la ciudad).
    # Mantenemos NUCLEO como último recurso para compat con el dataset clásico.
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
        # Para POINT el validator descarta `coordinates`; lo pasamos igualmente
        # por simetría con POLYGON / LINE_STRING.
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
    """Construye un nombre cuando el feature no aporta `name`/`NOMBRE`/`DENOMINACI`.

    Prioriza concatenar `tipoVia + nombreVia` (formato municipal: "CALLE DALIA")
    si llegan; si no, cae al `fallback_name` del profile; si tampoco, `None`
    y el contrato lo guardará como string vacío.
    """
    street_type = _first_present(props, "streetType", "TIPOVIA", "TIPO_VIA")
    street_name = _first_present(props, "streetName", "NOMBREVIA", "NOMBRE_VIA")
    if street_name:
        if street_type:
            return f"{street_type} {street_name}".strip()
        return str(street_name)
    if source is not None and source.fallback_name:
        return source.fallback_name
    return None


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
    """Importa una lista plana de features (sin source). Compat con tests legacy.

    Internamente delega en el orquestador multi-fuente con `source=None`.
    Útil cuando los tests pasan features sintéticos con propiedades explícitas.
    """
    return _run_import_paired(((feat, None) for feat in features), rdb)


def run_import_sources(
    sources: Iterable[tuple[Iterable[dict], Optional[SourceProfile]]],
    rdb: redis.Redis,
) -> dict[str, Any]:
    """Importa varios datasets con sus respectivos profiles.

    `sources` es una lista de pares `(features, profile)`. Cada feature se
    convierte con su profile correspondiente; el resumen incluye el desglose
    por `sourceDataset`.
    """
    paired: list[tuple[dict, Optional[SourceProfile]]] = []
    for features, profile in sources:
        for feat in features:
            paired.append((feat, profile))
    return _run_import_paired(iter(paired), rdb)


def _run_import_paired(
    features_with_profile: Iterator[tuple[dict, Optional[SourceProfile]]],
    rdb: redis.Redis,
) -> dict[str, Any]:
    """Orquestador real: limpia, indexa y resume.

    1. Borra todos los hashes `parking:*` del import previo (SCAN_ITER + DEL).
    2. Borra el sorted set `geo:parkings`.
    3. Por cada feature válido: GEOADD al índice geo + HSET con el contrato
       completo. Todo en un único pipeline para minimizar round-trips.
    4. Invalida la caché `cache:nearby:*` (best-effort: si Redis falla aquí,
       el TTL acabará limpiándola).
    5. Devuelve un resumen con totales + desglose por `sourceDataset`.

    Las `redis.ConnectionError` se propagan tal cual; el router las traducirá
    a HTTP 503.
    """
    pairs = list(features_with_profile)

    old_keys = list(rdb.scan_iter(match=f"{PARKING_KEY_PREFIX}*"))

    pipe = rdb.pipeline()
    if old_keys:
        pipe.delete(*old_keys)
    pipe.delete(GEO_KEY)

    imported = 0
    skipped = 0
    seen_ids: set[str] = set()
    # Desglose por dataset: clave = sourceDataset (o "" si no hay profile).
    per_source: dict[str, dict[str, int]] = {}

    for feature, profile in pairs:
        bucket_key = profile.source_dataset if profile is not None else ""
        bucket = per_source.setdefault(bucket_key, {"imported": 0, "skipped": 0})

        place = feature_to_place(feature, source=profile)
        if place is None:
            skipped += 1
            bucket["skipped"] += 1
            continue

        if place.id in seen_ids:
            # id duplicado entre features (mismo mslink en dos ficheros, o
            # colisión de hash improbable). HSET sobreescribe; lo logueamos.
            logger.warning(
                "id duplicado %r al importar (sourceDataset=%r); sobrescribiendo",
                place.id,
                bucket_key,
            )
        seen_ids.add(place.id)

        pipe.geoadd(GEO_KEY, (place.longitude, place.latitude, place.id))
        pipe.hset(
            f"{PARKING_KEY_PREFIX}{place.id}",
            mapping=place_to_redis_mapping(place),
        )
        imported += 1
        bucket["imported"] += 1

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
        "sources": [
            {
                "sourceDataset": name or None,
                "imported": stats["imported"],
                "skipped": stats["skipped"],
            }
            for name, stats in sorted(per_source.items())
        ],
    }


# ============================================================
# Descubrimiento y carga de ficheros desde disco
# ============================================================

def discover_geojson_files(data_dir: Path) -> list[Path]:
    """Lista los `*.geojson` del directorio, ordenados por nombre.

    Orden alfabético para que el resultado sea reproducible (y para que los
    contadores aparezcan en el mismo orden en logs y respuesta).
    """
    if not data_dir.exists() or not data_dir.is_dir():
        return []
    return sorted(p for p in data_dir.glob("*.geojson") if p.is_file())


def _load_features(path: Path) -> list[dict]:
    """Lee un GeoJSON y devuelve `features` (lista vacía si no hay)."""
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        return []
    features = data.get("features")
    return list(features) if isinstance(features, list) else []


def run_import_dir(data_dir: Path, rdb: redis.Redis) -> dict[str, Any]:
    """Importa todos los `*.geojson` de `data_dir` a Redis.

    Cada fichero se empareja con su `SourceProfile` (registry o genérico).
    Las `redis.ConnectionError` se propagan; el router las traduce a 503.
    Si un fichero individual está mal formado se logea y se cuenta como
    `skipped_files`, sin abortar el resto.
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
