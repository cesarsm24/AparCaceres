"""Tests del importador GeoJSON -> contrato móvil -> Redis.

Cubre:
- Derivación del id estable (mslink, fallbacks, ausencia).
- Punto representativo por tipo geométrico (point / polygon / line_string).
- Mapeo Feature -> ParkingPlaceOut con propiedades del dataset municipal.
- Round-trip ParkingPlaceOut <-> hash de Redis.
- Orquestación `run_import`: idempotencia, persistencia íntegra del contrato,
  invalidación de caché y tolerancia a features degenerados.

Para los tipos de geometría que el dataset real no incluye (polygon /
line_string) usamos GeoJSON sintético construido inline.
"""

from __future__ import annotations

import json

from app.config import CACHE_NEARBY_PREFIX, PARKING_KEY_PREFIX
from app.enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from app.importer import (
    SOURCE_REGISTRY,
    derive_stable_id,
    feature_to_place,
    place_from_redis_hash,
    place_to_redis_mapping,
    representative_point,
    run_import,
    run_import_sources,
)


_PROFILE_APARCAMIENTOS = SOURCE_REGISTRY["aparcamientos.geojson"]
_PROFILE_LINEA = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]


# ============================================================
# Fixtures de features (uno por tipo geométrico)
# ============================================================

def _point_feature() -> dict:
    """Feature de Point alineado con el dataset municipal real."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-6.34204232, 39.47848638]},
        "properties": {
            "CLASE": "APARCAMIENTO",
            "NOMBRE": "Escuela Politecnica",
            "NUCLEO": "CÁCERES",
            "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903",
        },
    }


def _polygon_feature() -> dict:
    """Polygon sintético que incluye campos modernos del contrato móvil."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-6.3994515, 39.4670139],
                    [-6.3991710, 39.4663191],
                    [-6.3991416, 39.4663258],
                    [-6.3994238, 39.4670207],
                    [-6.3994515, 39.4670139],
                ]
            ],
        },
        "properties": {
            "name": "Calle Dalia",
            "category": "street_line",
            "vehicleType": "car",
            "regulation": "free",
            "totalSpaces": 16,
            "streetName": "DALIA",
            "streetType": "CALLE",
            "district": "OESTE",
            "neighborhood": "EL JUNQUILLO",
            "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=5500",
        },
    }


def _line_string_feature() -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-6.4022597, 39.4775947],
                [-6.4022522, 39.4775983],
                [-6.4022077, 39.4776199],
            ],
        },
        "properties": {
            "name": "Superficie Esquiladores",
            "category": "street_line",
            "regulation": "free",
            "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=7700",
        },
    }


# Helper para los tests que usan un único source. Empaqueta la lista en el
# formato que espera `run_import_sources`.
def _import_with_source(features, profile, rdb):
    return run_import_sources([(features, profile)], rdb)


# ============================================================
# derive_stable_id
# ============================================================

def test_derive_stable_id_uses_mslink_namespaced_by_dataset():
    """El id resultante incluye el namespace del dataset (sin colisiones entre
    ficheros que reutilicen mslink)."""
    assert (
        derive_stable_id(
            {"URL": "http://sig.caceres.es/.../fichatoponimia.php?mslink=1903"},
            source=_PROFILE_APARCAMIENTOS,
        )
        == "aparcamientos:1903"
    )


def test_derive_stable_id_accepts_lowercase_url_key():
    assert (
        derive_stable_id(
            {"url": "https://example.org/x?mslink=42&foo=bar"},
            source=_PROFILE_LINEA,
        )
        == "aparcamientos_en_linea:42"
    )


def test_derive_stable_id_namespaces_explicit_id():
    """`id`/`ID` explícito gana sobre el hash, pero también se namespaceea."""
    assert (
        derive_stable_id({"id": "custom-123"}, source=_PROFILE_LINEA)
        == "aparcamientos_en_linea:custom-123"
    )
    assert (
        derive_stable_id({"ID": "  custom-456  "}, source=_PROFILE_LINEA)
        == "aparcamientos_en_linea:custom-456"
    )


def test_derive_stable_id_returns_none_without_source():
    """Sin source no podemos namespacear, así que mslink/URL devuelve None.

    Esto fuerza al importador a pasar siempre un `SourceProfile` y elimina la
    posibilidad de generar ids globales `aparcamiento-{mslink}` que pisarían
    datos entre datasets distintos."""
    assert derive_stable_id({"URL": "?mslink=1903"}) is None
    assert derive_stable_id({}) is None


def test_derive_stable_id_returns_none_when_no_signal_with_source():
    """Sin mslink, sin id explícito y sin geometría no podemos generar fallback."""
    assert (
        derive_stable_id({"URL": "http://example.org/no-mslink-here"}, source=_PROFILE_LINEA)
        is None
    )


def test_derive_stable_id_namespaces_collide_only_within_dataset():
    """Mismo `mslink=3` en dos ficheros distintos -> ids distintos."""
    a = derive_stable_id(
        {"URL_FICHA": "?mslink=3"},
        source=SOURCE_REGISTRY["parking_bicis.geojson"],
    )
    b = derive_stable_id(
        {"URL_FICHA": "?mslink=3"},
        source=SOURCE_REGISTRY["parking_motos_areas.geojson"],
    )
    assert a == "parking_bicis:3"
    assert b == "parking_motos_areas:3"
    assert a != b


# ============================================================
# representative_point
# ============================================================

def test_representative_point_for_point_geometry():
    assert representative_point(
        ParkingGeometryType.POINT, [-6.37, 39.47]
    ) == (-6.37, 39.47)


def test_representative_point_returns_none_for_invalid_point():
    assert representative_point(ParkingGeometryType.POINT, None) is None
    assert representative_point(ParkingGeometryType.POINT, [1]) is None
    assert representative_point(ParkingGeometryType.POINT, "broken") is None


def test_representative_point_for_polygon_is_centroid_of_first_ring():
    # Anillo cuadrado cerrado en (0,0)-(2,0)-(2,2)-(0,2)-(0,0) -> centroide (1,1).
    coords = [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]
    assert representative_point(ParkingGeometryType.POLYGON, coords) == (1.0, 1.0)


def test_representative_point_for_polygon_handles_non_closed_ring():
    # Sin punto de cierre duplicado el promedio es el de los 4 puntos.
    coords = [[[0, 0], [2, 0], [2, 2], [0, 2]]]
    assert representative_point(ParkingGeometryType.POLYGON, coords) == (1.0, 1.0)


def test_representative_point_for_line_string_is_middle_index():
    coords = [[0, 0], [1, 1], [2, 2]]
    assert representative_point(
        ParkingGeometryType.LINE_STRING, coords
    ) == (1.0, 1.0)


def test_representative_point_returns_none_for_degenerate_polygon():
    # Anillo de 2 puntos -> coerce_polygon lo descarta -> None.
    assert representative_point(
        ParkingGeometryType.POLYGON, [[[0, 0], [1, 1]]]
    ) is None


# ============================================================
# feature_to_place
# ============================================================

def test_feature_to_place_point_maps_municipal_properties():
    place = feature_to_place(_point_feature(), source=_PROFILE_APARCAMIENTOS)
    assert place is not None
    assert place.id == "aparcamientos:1903"
    assert place.name == "Escuela Politecnica"
    assert place.geometryType == ParkingGeometryType.POINT
    # POINT no almacena coordinates en el contrato móvil.
    assert place.coordinates is None
    # Lat/Lon vienen de las coordenadas (orden GeoJSON: [lon, lat]).
    assert place.longitude == -6.34204232
    assert place.latitude == 39.47848638
    # Defaults de enum cuando el dataset no aporta los campos.
    assert place.category == ParkingCategory.PARKING
    assert place.vehicleType == ParkingVehicleType.CAR
    assert place.regulation == ParkingRegulation.FREE
    # `NUCLEO` se mapea a `district`; URL al campo `urlFicha`.
    assert place.district == "CÁCERES"
    assert place.urlFicha == _point_feature()["properties"]["URL"]
    # `sourceDataset` viene del profile, no del feature.
    assert place.sourceDataset == "aparcamientos"


def test_feature_to_place_polygon_preserves_coordinates_and_total_spaces():
    place = feature_to_place(_polygon_feature(), source=_PROFILE_LINEA)
    assert place is not None
    assert place.id == "aparcamientos_en_linea:5500"
    assert place.geometryType == ParkingGeometryType.POLYGON
    assert place.totalSpaces == 16
    assert place.category == ParkingCategory.STREET_LINE
    # POLYGON: list[ring] con tuplas (lon, lat).
    assert place.coordinates is not None
    assert len(place.coordinates) == 1
    assert place.coordinates[0][0] == (-6.3994515, 39.4670139)
    # Lat/Lon deben caer en el centroide, dentro del bounding box.
    assert -6.40 < place.longitude < -6.39
    assert 39.46 < place.latitude < 39.47


def test_feature_to_place_line_string_keeps_track_coordinates():
    place = feature_to_place(_line_string_feature(), source=_PROFILE_LINEA)
    assert place is not None
    assert place.id == "aparcamientos_en_linea:7700"
    assert place.geometryType == ParkingGeometryType.LINE_STRING
    assert place.coordinates == [
        (-6.4022597, 39.4775947),
        (-6.4022522, 39.4775983),
        (-6.4022077, 39.4776199),
    ]


def test_feature_to_place_returns_none_for_unsupported_geometry():
    """`GeometryCollection` no se soporta — el contrato móvil expone una
    geometría por place. Multi* sí se soporta vía colapso a su variante
    simple (ver tests de MultiPolygon)."""
    assert (
        feature_to_place(
            {
                "type": "Feature",
                "geometry": {"type": "GeometryCollection", "geometries": []},
                "properties": {"URL": "?mslink=1"},
            },
            source=_PROFILE_LINEA,
        )
        is None
    )


def test_feature_to_place_returns_none_when_id_cannot_be_derived():
    # Sin source ni id explícito → no hay forma de generar un id estable.
    assert (
        feature_to_place(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"NOMBRE": "Sin URL"},
            }
        )
        is None
    )


# ============================================================
# place_to_redis_mapping / place_from_redis_hash (round-trip)
# ============================================================

def test_place_to_redis_mapping_omits_none_fields_and_serializes_coordinates():
    place = feature_to_place(_polygon_feature(), source=_PROFILE_LINEA)
    assert place is not None
    mapping = place_to_redis_mapping(place)

    # Solo strings.
    for k, v in mapping.items():
        assert isinstance(v, str), f"{k}={v!r} debería ser str"

    # Enums como wire string.
    assert mapping["category"] == "street_line"
    assert mapping["geometryType"] == "polygon"

    # Coordinates serializado a JSON parseable.
    coords = json.loads(mapping["coordinates"])
    assert coords[0][0] == [-6.3994515, 39.4670139]

    # Campos indexables para Redis Stack / RediSearch.
    assert mapping["location"].startswith("-6.399")
    assert "calle dalia" in mapping["searchText"]

    # Campos None del contrato no aparecen en el hash.
    assert "imageUrl" not in mapping
    assert "management" not in mapping


def test_place_to_redis_mapping_skips_coordinates_for_point():
    place = feature_to_place(_point_feature(), source=_PROFILE_APARCAMIENTOS)
    assert place is not None
    mapping = place_to_redis_mapping(place)
    assert "coordinates" not in mapping
    assert mapping["geometryType"] == "point"


def test_place_round_trip_through_redis_hash_preserves_contract():
    """El round-trip por el hash no debe perder ningún campo del contrato."""
    cases = (
        (_point_feature, _PROFILE_APARCAMIENTOS),
        (_polygon_feature, _PROFILE_LINEA),
        (_line_string_feature, _PROFILE_LINEA),
    )
    for build, profile in cases:
        original = feature_to_place(build(), source=profile)
        assert original is not None

        mapping = place_to_redis_mapping(original)
        restored = place_from_redis_hash(mapping)

        # JSON de ambos modelos debe coincidir literalmente.
        assert restored.model_dump_json() == original.model_dump_json(), (
            f"round-trip rompe el contrato para {original.geometryType}"
        )


# ============================================================
# run_import (orquestador completo contra fake_redis)
# ============================================================

def _all_geometries_sources() -> list[tuple[list[dict], object]]:
    """Pareja (features, profile) para los 3 tipos geométricos del fixture."""
    return [
        ([_point_feature()], _PROFILE_APARCAMIENTOS),
        ([_polygon_feature(), _line_string_feature()], _PROFILE_LINEA),
    ]


def test_run_import_persists_full_contract_for_each_geometry(fake_redis):
    summary = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary["status"] == "ok"
    assert summary["imported"] == 3
    assert summary["skipped"] == 0

    # Cada hash contiene los campos clave del contrato y se puede reconstruir.
    expected_ids = (
        "aparcamientos:1903",
        "aparcamientos_en_linea:5500",
        "aparcamientos_en_linea:7700",
    )
    for parking_id in expected_ids:
        hash_data = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")
        assert hash_data["id"] == parking_id
        # Campos obligatorios del contrato presentes y serializados como string.
        for required in ("name", "category", "vehicleType", "regulation",
                         "geometryType", "latitude", "longitude", "location", "searchText"):
            assert required in hash_data, f"{parking_id} sin {required}"
        # Reconstrucción coherente con el feature original.
        place_from_redis_hash(hash_data)


def test_run_import_polygon_stores_coordinates_as_parseable_json(fake_redis):
    run_import_sources([([_polygon_feature()], _PROFILE_LINEA)], fake_redis)
    hash_data = fake_redis.hgetall(
        f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:5500"
    )
    assert hash_data["geometryType"] == "polygon"
    assert hash_data["totalSpaces"] == "16"
    coords = json.loads(hash_data["coordinates"])
    assert coords[0][0] == [-6.3994515, 39.4670139]


def test_run_import_line_string_stores_track(fake_redis):
    run_import_sources([([_line_string_feature()], _PROFILE_LINEA)], fake_redis)
    hash_data = fake_redis.hgetall(
        f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:7700"
    )
    assert hash_data["geometryType"] == "line_string"
    coords = json.loads(hash_data["coordinates"])
    assert coords == [
        [-6.4022597, 39.4775947],
        [-6.4022522, 39.4775983],
        [-6.4022077, 39.4776199],
    ]


def test_run_import_point_does_not_store_coordinates_field(fake_redis):
    run_import_sources([([_point_feature()], _PROFILE_APARCAMIENTOS)], fake_redis)
    hash_data = fake_redis.hgetall(
        f"{PARKING_KEY_PREFIX}aparcamientos:1903"
    )
    assert hash_data["geometryType"] == "point"
    assert "coordinates" not in hash_data


def test_run_import_is_idempotent_and_clears_stale_entries(fake_redis):
    """Reimportar con un dataset distinto debe dejar Redis solo con lo nuevo."""
    # Primera carga: los 3 features.
    run_import_sources(_all_geometries_sources(), fake_redis)
    assert f"{PARKING_KEY_PREFIX}aparcamientos:1903" in fake_redis.hashes

    # Segunda carga: solo el LineString. El resto debe desaparecer.
    summary = run_import_sources(
        [([_line_string_feature()], _PROFILE_LINEA)], fake_redis
    )
    assert summary["imported"] == 1

    surviving = [k for k in fake_redis.hashes if k.startswith(PARKING_KEY_PREFIX)]
    assert surviving == [f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:7700"]


def test_run_import_invalidates_nearby_cache(fake_redis):
    # Sembramos varias entradas de caché previas a la importación.
    fake_redis.setex(f"{CACHE_NEARBY_PREFIX}39.4700:-6.3700:500", 60, "[]")
    fake_redis.setex(f"{CACHE_NEARBY_PREFIX}39.4800:-6.3800:1000", 60, "[]")
    # Y una clave ajena que NO debe tocarse.
    fake_redis.setex("other:key", 60, "stay")

    summary = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary["cache_invalidated"] == 2
    assert not any(
        k.startswith(CACHE_NEARBY_PREFIX) for k in fake_redis.strings
    )
    assert fake_redis.get("other:key") == "stay"


def test_run_import_disambiguates_duplicate_municipal_ids(fake_redis):
    first = _point_feature()
    second = _point_feature()
    second["properties"] = dict(second["properties"])
    second["properties"]["NOMBRE"] = "Duplicado"
    second["geometry"] = {"type": "Point", "coordinates": [-6.34, 39.47]}

    summary = run_import_sources([([first, second], _PROFILE_APARCAMIENTOS)], fake_redis)

    assert summary["imported"] == 2
    assert summary["ids_disambiguated"] == 1
    assert f"{PARKING_KEY_PREFIX}aparcamientos:1903" in fake_redis.hashes
    assert f"{PARKING_KEY_PREFIX}aparcamientos:1903:2" in fake_redis.hashes


def test_run_import_skips_invalid_features_without_failing(fake_redis):
    """Features con geometría rota se cuentan como skipped sin abortar."""
    bad_features = [
        # Geometría no soportada (GeometryCollection no entra al contrato).
        {
            "type": "Feature",
            "geometry": {"type": "GeometryCollection", "geometries": []},
            "properties": {"URL": "?mslink=999"},
        },
        # Feature sin geometría: descarta limpiamente.
        {
            "type": "Feature",
            "geometry": None,
            "properties": {"id": "broken"},
        },
    ]
    summary = run_import_sources(
        [
            ([_point_feature()], _PROFILE_APARCAMIENTOS),
            (bad_features, _PROFILE_LINEA),
        ],
        fake_redis,
    )
    assert summary["imported"] == 1
    assert summary["skipped"] == 2
    assert list(fake_redis.hashes.keys()) == [f"{PARKING_KEY_PREFIX}aparcamientos:1903"]


def test_run_import_stores_representative_location_for_search(fake_redis):
    run_import_sources(_all_geometries_sources(), fake_redis)

    # POINT: lat/lon = la coordenada original.
    point_hash = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}aparcamientos:1903")
    lon, lat = (float(v) for v in point_hash["location"].split(",", 1))
    assert (lon, lat) == (-6.34204232, 39.47848638)

    # POLYGON: dentro del bounding box del primer anillo.
    polygon_hash = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:5500")
    lon, lat = (float(v) for v in polygon_hash["location"].split(",", 1))
    assert -6.40 < lon < -6.39
    assert 39.46 < lat < 39.47

    # LINE_STRING: el punto medio por índice.
    line_hash = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:7700")
    lon, lat = (float(v) for v in line_hash["location"].split(",", 1))
    assert (lon, lat) == (-6.4022522, 39.4775983)
