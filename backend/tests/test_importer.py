"""Tests del importador GeoJSON a Redis.

Verifican derivación de ids estables, cálculo de puntos representativos,
normalización de features, round-trip por hashes Redis y orquestación completa
de importación con doble buffer e invalidación de caché.
"""

from __future__ import annotations

import json

from app.core.config import CACHE_VERSION_KEY, PARKING_KEY_PREFIX
from app.enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from app.infra.redis.importer import (
    SOURCE_REGISTRY,
    derive_stable_id,
    feature_to_place,
    place_from_redis_hash,
    place_to_redis_mapping,
    representative_point,
    run_import_sources,
)

_PROFILE_APARCAMIENTOS = SOURCE_REGISTRY["aparcamientos.geojson"]
_PROFILE_LINEA = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]


def _point_feature() -> dict:
    """Devuelve un feature de punto representativo del dataset municipal."""
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
    """Devuelve un feature poligonal sintético con campos de contrato."""
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
    """Devuelve un feature lineal sintético."""
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


def _import_with_source(features, profile, rdb):
    """Ejecuta una importación de un único origen."""
    return run_import_sources([(features, profile)], rdb)


def test_derive_stable_id_uses_mslink_namespaced_by_dataset():
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
    assert (
        derive_stable_id({"id": "custom-123"}, source=_PROFILE_LINEA)
        == "aparcamientos_en_linea:custom-123"
    )
    assert (
        derive_stable_id({"ID": "  custom-456  "}, source=_PROFILE_LINEA)
        == "aparcamientos_en_linea:custom-456"
    )


def test_derive_stable_id_returns_none_without_source():
    assert derive_stable_id({"URL": "?mslink=1903"}) is None
    assert derive_stable_id({}) is None


def test_derive_stable_id_returns_none_when_no_signal_with_source():
    assert (
        derive_stable_id({"URL": "http://example.org/no-mslink-here"}, source=_PROFILE_LINEA)
        is None
    )


def test_derive_stable_id_namespaces_collide_only_within_dataset():
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


def test_representative_point_for_point_geometry():
    assert representative_point(
        ParkingGeometryType.POINT,
        [-6.37, 39.47],
    ) == (-6.37, 39.47)


def test_representative_point_returns_none_for_invalid_point():
    assert representative_point(ParkingGeometryType.POINT, None) is None
    assert representative_point(ParkingGeometryType.POINT, [1]) is None
    assert representative_point(ParkingGeometryType.POINT, "broken") is None


def test_representative_point_for_polygon_is_centroid_of_first_ring():
    coords = [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]

    assert representative_point(ParkingGeometryType.POLYGON, coords) == (1.0, 1.0)


def test_representative_point_for_polygon_handles_non_closed_ring():
    coords = [[[0, 0], [2, 0], [2, 2], [0, 2]]]

    assert representative_point(ParkingGeometryType.POLYGON, coords) == (1.0, 1.0)


def test_representative_point_for_line_string_is_middle_index():
    coords = [[0, 0], [1, 1], [2, 2]]

    assert representative_point(
        ParkingGeometryType.LINE_STRING,
        coords,
    ) == (1.0, 1.0)


def test_representative_point_returns_none_for_degenerate_polygon():
    assert representative_point(
        ParkingGeometryType.POLYGON,
        [[[0, 0], [1, 1]]],
    ) is None


def test_polygon_centroid_weights_by_area_for_asymmetric_l():
    coords = [[[0, 0], [10, 0], [10, 1], [1, 1], [1, 3], [0, 3], [0, 0]]]

    centroid = representative_point(ParkingGeometryType.POLYGON, coords)

    assert centroid is not None

    cx, cy = centroid
    assert 0 <= cx <= 10 and 0 <= cy <= 1

    promedio_x = (0 + 10 + 10 + 1 + 1 + 0) / 6
    promedio_y = (0 + 0 + 1 + 1 + 3 + 3) / 6

    assert abs(cx - promedio_x) > 0.5 or abs(cy - promedio_y) > 0.5


def test_polygon_centroid_falls_back_when_collinear():
    coords = [[[0, 0], [1, 0], [2, 0]]]

    assert representative_point(ParkingGeometryType.POLYGON, coords) == (1.0, 0.0)


def test_feature_to_place_point_maps_municipal_properties():
    place = feature_to_place(_point_feature(), source=_PROFILE_APARCAMIENTOS)

    assert place is not None
    assert place.id == "aparcamientos:1903"
    assert place.name == "Escuela Politecnica"
    assert place.geometryType == ParkingGeometryType.POINT
    assert place.coordinates is None
    assert place.longitude == -6.34204232
    assert place.latitude == 39.47848638
    assert place.category == ParkingCategory.PARKING
    assert place.vehicleType == ParkingVehicleType.CAR
    assert place.regulation == ParkingRegulation.FREE
    assert place.district == "CÁCERES"
    assert place.urlFicha == _point_feature()["properties"]["URL"]
    assert place.sourceDataset == "aparcamientos"


def test_feature_to_place_polygon_preserves_coordinates_and_total_spaces():
    place = feature_to_place(_polygon_feature(), source=_PROFILE_LINEA)

    assert place is not None
    assert place.id == "aparcamientos_en_linea:5500"
    assert place.geometryType == ParkingGeometryType.POLYGON
    assert place.totalSpaces == 16
    assert place.category == ParkingCategory.STREET_LINE
    assert place.coordinates is not None
    assert len(place.coordinates) == 1
    assert place.coordinates[0][0] == (-6.3994515, 39.4670139)
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


def test_place_to_redis_mapping_omits_none_fields_and_serializes_coordinates():
    place = feature_to_place(_polygon_feature(), source=_PROFILE_LINEA)

    assert place is not None

    mapping = place_to_redis_mapping(place)

    for key, value in mapping.items():
        assert isinstance(value, str), f"{key}={value!r} debería ser str"

    assert mapping["category"] == "street_line"
    assert mapping["geometryType"] == "polygon"

    coords = json.loads(mapping["coordinates"])

    assert coords[0][0] == [-6.3994515, 39.4670139]
    assert mapping["location"].startswith("-6.399")
    assert "calle dalia" in mapping["searchText"]
    assert "imageUrl" not in mapping
    assert "management" not in mapping


def test_place_to_redis_mapping_skips_coordinates_for_point():
    place = feature_to_place(_point_feature(), source=_PROFILE_APARCAMIENTOS)

    assert place is not None

    mapping = place_to_redis_mapping(place)

    assert "coordinates" not in mapping
    assert mapping["geometryType"] == "point"


def test_place_round_trip_through_redis_hash_preserves_contract():
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

        assert restored.model_dump_json() == original.model_dump_json(), (
            f"round-trip rompe el contrato para {original.geometryType}"
        )


def _all_geometries_sources() -> list[tuple[list[dict], object]]:
    """Agrupa los fixtures por origen para probar la importación completa."""
    return [
        ([_point_feature()], _PROFILE_APARCAMIENTOS),
        ([_polygon_feature(), _line_string_feature()], _PROFILE_LINEA),
    ]


def test_run_import_persists_full_contract_for_each_geometry(fake_redis):
    summary = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary["status"] == "ok"
    assert summary["imported"] == 3
    assert summary["skipped"] == 0

    expected_ids = (
        "aparcamientos:1903",
        "aparcamientos_en_linea:5500",
        "aparcamientos_en_linea:7700",
    )

    for parking_id in expected_ids:
        hash_data = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}{parking_id}")

        assert hash_data["id"] == parking_id

        for required in (
            "name",
            "category",
            "vehicleType",
            "regulation",
            "geometryType",
            "latitude",
            "longitude",
            "location",
            "searchText",
        ):
            assert required in hash_data, f"{parking_id} sin {required}"

        place_from_redis_hash(hash_data)


def test_run_import_polygon_stores_coordinates_as_parseable_json(fake_redis):
    run_import_sources([([_polygon_feature()], _PROFILE_LINEA)], fake_redis)

    hash_data = fake_redis.hgetall(
        f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:5500"
    )
    coords = json.loads(hash_data["coordinates"])

    assert hash_data["geometryType"] == "polygon"
    assert hash_data["totalSpaces"] == "16"
    assert coords[0][0] == [-6.3994515, 39.4670139]


def test_run_import_line_string_stores_track(fake_redis):
    run_import_sources([([_line_string_feature()], _PROFILE_LINEA)], fake_redis)

    hash_data = fake_redis.hgetall(
        f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:7700"
    )
    coords = json.loads(hash_data["coordinates"])

    assert hash_data["geometryType"] == "line_string"
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
    run_import_sources(_all_geometries_sources(), fake_redis)

    assert f"{PARKING_KEY_PREFIX}aparcamientos:1903" in fake_redis.hashes

    summary = run_import_sources(
        [([_line_string_feature()], _PROFILE_LINEA)],
        fake_redis,
    )

    assert summary["imported"] == 1

    surviving = [key for key in fake_redis.hashes if key.startswith(PARKING_KEY_PREFIX)]

    assert surviving == [f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:7700"]


def test_run_import_uses_double_buffer_and_leaves_staging_clean(fake_redis):
    from app.core.config import STAGING_KEY_PREFIX

    summary = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary["status"] == "ok"

    staging_leftovers = [
        key for key in fake_redis.hashes if key.startswith(STAGING_KEY_PREFIX)
    ]

    assert staging_leftovers == []

    active_keys = [
        key for key in fake_redis.hashes if key.startswith(PARKING_KEY_PREFIX)
    ]

    assert active_keys


def test_run_import_recovers_from_orphan_staging(fake_redis):
    from app.core.config import STAGING_KEY_PREFIX

    fake_redis.hashes[f"{STAGING_KEY_PREFIX}leftover:1"] = {"id": "leftover:1"}
    fake_redis.hashes[f"{STAGING_KEY_PREFIX}leftover:2"] = {"id": "leftover:2"}

    summary = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary["status"] == "ok"

    staging_leftovers = [
        key for key in fake_redis.hashes if key.startswith(STAGING_KEY_PREFIX)
    ]

    assert staging_leftovers == []


def test_run_import_bumps_cache_version(fake_redis):
    assert fake_redis.get(CACHE_VERSION_KEY) is None

    summary = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary["cache_version"] == 1
    assert fake_redis.get(CACHE_VERSION_KEY) == "1"

    summary2 = run_import_sources(_all_geometries_sources(), fake_redis)

    assert summary2["cache_version"] == 2
    assert fake_redis.get(CACHE_VERSION_KEY) == "2"


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
    bad_features = [
        {
            "type": "Feature",
            "geometry": {"type": "GeometryCollection", "geometries": []},
            "properties": {"URL": "?mslink=999"},
        },
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

    point_hash = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}aparcamientos:1903")
    lon, lat = (float(value) for value in point_hash["location"].split(",", 1))

    assert (lon, lat) == (-6.34204232, 39.47848638)

    polygon_hash = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:5500")
    lon, lat = (float(value) for value in polygon_hash["location"].split(",", 1))

    assert -6.40 < lon < -6.39
    assert 39.46 < lat < 39.47

    line_hash = fake_redis.hgetall(f"{PARKING_KEY_PREFIX}aparcamientos_en_linea:7700")
    lon, lat = (float(value) for value in line_hash["location"].split(",", 1))

    assert (lon, lat) == (-6.4022522, 39.4775983)