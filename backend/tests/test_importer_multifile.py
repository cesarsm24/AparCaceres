"""Tests del importador multi-fichero.

Verifican perfiles por fichero, tolerancia a propiedades municipales
heterogéneas, clasificación de URLs, ids deterministas, procesamiento de
directorios e integridad del contrato tras persistir en Redis.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import PARKING_KEY_PREFIX
from app.enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from app.infra.redis.importer import (
    SOURCE_REGISTRY,
    derive_stable_id,
    discover_geojson_files,
    feature_to_place,
    place_from_redis_hash,
    profile_for,
    run_import_dir,
    run_import_sources,
)


def _write_geojson(directory: Path, filename: str, features: list[dict]) -> Path:
    """Escribe un FeatureCollection mínimo en el directorio indicado."""
    path = directory / filename
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    return path


def _line_string(coords):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {},
    }


def _polygon(ring):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {},
    }


def _point(lon: float, lat: float, properties: dict | None = None):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties or {},
    }


def test_source_registry_covers_all_active_files():
    expected = {
        "aparcamientos.geojson",
        "parkings.geojson",
        "aparcamientos_en_bateria.geojson",
        "aparcamientos_en_linea.geojson",
        "zona_azul.geojson",
        "carga_descarga.geojson",
        "movilidad_reducida.geojson",
        "parking_bicis.geojson",
        "parking_motos_areas.geojson",
        "parking_motos_puntos.geojson",
    }

    assert expected.issubset(SOURCE_REGISTRY.keys())


def test_profile_for_known_file_returns_registered_profile():
    profile = profile_for("zona_azul.geojson")

    assert profile.default_category == ParkingCategory.BLUE_ZONE
    assert profile.default_regulation == ParkingRegulation.BLUE_ZONE
    assert profile.short_id_prefix == "azul"


def test_profile_for_unknown_file_returns_generic_with_stem():
    profile = profile_for("ataques_marcianos.geojson")

    assert profile.default_category == ParkingCategory.PARKING
    assert profile.default_vehicle_type == ParkingVehicleType.CAR
    assert profile.default_regulation == ParkingRegulation.FREE
    assert profile.source_dataset == "ataques_marcianos"


def test_feature_with_empty_properties_inherits_profile_defaults():
    feat = _line_string([
        [-6.401, 39.477],
        [-6.402, 39.478],
        [-6.403, 39.479],
    ])
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]

    place = feature_to_place(feat, source=profile)

    assert place is not None
    assert place.category == profile.default_category
    assert place.vehicleType == profile.default_vehicle_type
    assert place.regulation == profile.default_regulation
    assert place.sourceDataset == profile.source_dataset
    assert place.name == profile.fallback_name
    assert place.geometryType == ParkingGeometryType.LINE_STRING


def test_bicis_profile_yields_bike_vehicle_type():
    feat = _point(-6.37, 39.47)
    profile = SOURCE_REGISTRY["parking_bicis.geojson"]

    place = feature_to_place(feat, source=profile)

    assert place is not None
    assert place.vehicleType == ParkingVehicleType.BIKE
    assert place.category == ParkingCategory.BICYCLE


def test_motos_profile_yields_motorbike_vehicle_type():
    feat = _point(-6.37, 39.47)

    place = feature_to_place(
        feat,
        source=SOURCE_REGISTRY["parking_motos_puntos.geojson"],
    )

    assert place is not None
    assert place.vehicleType == ParkingVehicleType.MOTORBIKE
    assert place.category == ParkingCategory.MOTORBIKE


def test_carga_descarga_profile_overrides_misleading_tipo_field():
    feat = _polygon([
        [-6.38, 39.47],
        [-6.38, 39.48],
        [-6.37, 39.48],
        [-6.38, 39.47],
    ])
    feat["properties"] = {"TIPO": "ZONA AZUL", "PLAZAS": "2"}

    place = feature_to_place(
        feat,
        source=SOURCE_REGISTRY["carga_descarga.geojson"],
    )

    assert place is not None
    assert place.category == ParkingCategory.LOADING
    assert place.regulation == ParkingRegulation.LOADING


def test_feature_with_codigovia_single_word_does_not_crash():
    feat = _polygon([
        [-6.38, 39.47],
        [-6.38, 39.48],
        [-6.37, 39.48],
        [-6.38, 39.47],
    ])
    feat["properties"] = {
        "TIPO": "EN BATERIA",
        "PLAZAS": 8,
        "CODIGOVIA": 4142,
        "TIPOVIA": "AVDA",
        "NOMBREVIA": "DEL FERROCARRIL",
        "URL": "https://sig.caceres.es/serweb/fichasig/fichacalle.php?codigo=4142",
    }

    place = feature_to_place(
        feat,
        source=SOURCE_REGISTRY["aparcamientos_en_bateria.geojson"],
    )

    assert place is not None
    assert place.streetName == "DEL FERROCARRIL"
    assert place.streetType == "AVDA"
    assert place.totalSpaces == 8
    assert place.urlVia and "fichacalle.php" in place.urlVia
    assert place.urlFicha is None


def test_feature_with_codigo_via_underscore_variant_normalizes_same():
    feat = _point(-6.37, 39.47)
    feat["properties"] = {
        "CODIGO_VIA": 4143,
        "NOMBRE_VIA": "DEL FERROCARRIL",
        "TIPO_VIA": "AVDA",
        "BARRIO": "ESTACION",
        "DISTRITO": "OESTE",
        "URL_FICHA": "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=999",
        "URL_VIA": "https://sig.caceres.es/serweb/fichasig/fichacalle.php?codigo=4143",
        "URL_FOTO": "https://sig.caceres.es/foto.jpg",
        "GESTION": "AYUNTAMIENTO",
    }

    place = feature_to_place(
        feat,
        source=SOURCE_REGISTRY["movilidad_reducida.geojson"],
    )

    assert place is not None
    assert place.streetName == "DEL FERROCARRIL"
    assert place.streetType == "AVDA"
    assert place.neighborhood == "ESTACION"
    assert place.district == "OESTE"
    assert place.imageUrl == "https://sig.caceres.es/foto.jpg"
    assert place.urlFicha and "fichatoponimia.php" in place.urlFicha
    assert place.urlVia and "fichacalle.php" in place.urlVia
    assert place.management == "AYUNTAMIENTO"


def test_parkings_uses_denominaci_truncated_shapefile_field():
    feat = _point(-6.374084, 39.475736)
    feat["properties"] = {
        "CLASE": "PARKING",
        "DENOMINACI": "Obispo Galarza",
        "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1882",
    }

    place = feature_to_place(feat, source=SOURCE_REGISTRY["parkings.geojson"])

    assert place is not None
    assert place.name == "Obispo Galarza"
    assert place.category == ParkingCategory.PAID_PARKING
    assert place.regulation == ParkingRegulation.PAID
    assert place.id == "parkings:1882"


def test_url_classification_routes_image_url_to_imageurl():
    feat = _point(-6.37, 39.47)
    feat["properties"] = {
        "URL": "https://sig.caceres.es/fotosOriginales/PARKING_BICIS/134_1.JPG",
    }

    place = feature_to_place(feat, source=SOURCE_REGISTRY["parking_bicis.geojson"])

    assert place is not None
    assert place.imageUrl is not None and place.imageUrl.endswith("134_1.JPG")
    assert place.urlFicha is None
    assert place.urlVia is None


def test_url_classification_routes_fichacalle_to_urlvia():
    feat = _polygon([
        [-6.38, 39.47],
        [-6.38, 39.48],
        [-6.37, 39.48],
        [-6.38, 39.47],
    ])
    feat["properties"] = {
        "URL": "https://sig.caceres.es/serweb/fichasig/fichacalle.php?codigo=42",
    }

    place = feature_to_place(feat, source=SOURCE_REGISTRY["zona_azul.geojson"])

    assert place is not None
    assert place.urlVia and "fichacalle.php" in place.urlVia
    assert place.urlFicha is None


def test_derive_stable_id_falls_back_to_hash_when_source_present():
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]
    coords = [[-6.40, 39.47], [-6.41, 39.48]]

    parking_id = derive_stable_id(
        {},
        source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )

    assert parking_id is not None

    namespace, fingerprint = parking_id.split(":", 1)

    assert namespace == "aparcamientos_en_linea"
    assert len(fingerprint) == 20


def test_hash_id_is_deterministic_across_calls():
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]
    coords = [[-6.40, 39.47], [-6.41, 39.48]]

    first = derive_stable_id(
        {},
        source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )
    second = derive_stable_id(
        {},
        source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )

    assert first == second


def test_hash_ids_differ_between_distinct_features_in_same_source():
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]

    first = derive_stable_id(
        {},
        source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=[[-6.40, 39.47], [-6.41, 39.48]],
    )
    second = derive_stable_id(
        {},
        source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=[[-6.50, 39.50], [-6.51, 39.51]],
    )

    assert first != second


def test_hash_ids_namespace_by_profile_prefix():
    coords = [[-6.40, 39.47], [-6.41, 39.48]]

    first = derive_stable_id(
        {},
        source=SOURCE_REGISTRY["aparcamientos_en_bateria.geojson"],
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )
    second = derive_stable_id(
        {},
        source=SOURCE_REGISTRY["aparcamientos_en_linea.geojson"],
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )

    assert first is not None and second is not None
    assert first.split(":", 1)[0] == "aparcamientos_en_bateria"
    assert second.split(":", 1)[0] == "aparcamientos_en_linea"
    assert first != second


def test_discover_geojson_files_lists_only_geojson_sorted(tmp_path: Path):
    _write_geojson(tmp_path, "b.geojson", [])
    _write_geojson(tmp_path, "a.geojson", [])
    (tmp_path / "leeme.txt").write_text("ignorame", encoding="utf-8")

    files = discover_geojson_files(tmp_path)

    assert [path.name for path in files] == ["a.geojson", "b.geojson"]


def test_discover_geojson_files_returns_empty_for_missing_dir(tmp_path: Path):
    assert discover_geojson_files(tmp_path / "no-existe") == []


def test_run_import_sources_imports_per_profile_defaults(fake_redis):
    linea_features = [
        _line_string([[-6.40, 39.47], [-6.41, 39.48]]),
        _line_string([[-6.42, 39.49], [-6.43, 39.50]]),
    ]
    bici_features = [
        _point(-6.37, 39.47, {"NOMBRE_VIA": "COLON", "TIPO_VIA": "CALLE", "PLAZAS": "5"}),
    ]

    summary = run_import_sources(
        [
            (linea_features, SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]),
            (bici_features, SOURCE_REGISTRY["parking_bicis.geojson"]),
        ],
        fake_redis,
    )

    assert summary["imported"] == 3
    assert summary["skipped"] == 0
    assert summary["status"] == "ok"

    by_dataset = {source["sourceDataset"]: source for source in summary["sources"]}

    assert by_dataset["aparcamientos_en_linea"]["imported"] == 2
    assert by_dataset["parking_bicis"]["imported"] == 1
    assert sum(1 for key in fake_redis.hashes if key.startswith(PARKING_KEY_PREFIX)) == 3


def test_run_import_dir_processes_all_files_in_directory(tmp_path: Path, fake_redis):
    _write_geojson(tmp_path, "parking_bicis.geojson", [
        _point(-6.37, 39.47, {"NOMBRE_VIA": "COLON", "TIPO_VIA": "CALLE", "PLAZAS": "5"}),
    ])
    _write_geojson(tmp_path, "aparcamientos_en_linea.geojson", [
        _line_string([[-6.40, 39.47], [-6.41, 39.48]]),
        _line_string([[-6.42, 39.49], [-6.43, 39.50]]),
    ])
    _write_geojson(tmp_path, "zona_azul.geojson", [
        _polygon([[-6.38, 39.47], [-6.38, 39.48], [-6.37, 39.48], [-6.38, 39.47]]),
    ])

    summary = run_import_dir(tmp_path, fake_redis)

    assert summary["files_processed"] == 3
    assert summary["files_skipped"] == []
    assert summary["imported"] == 4
    assert summary["skipped"] == 0

    by_dataset = {source["sourceDataset"]: source for source in summary["sources"]}

    assert by_dataset["parking_bicis"]["imported"] == 1
    assert by_dataset["aparcamientos_en_linea"]["imported"] == 2
    assert by_dataset["zona_azul"]["imported"] == 1

    linea_keys = [
        key for key in fake_redis.hashes
        if key.startswith(PARKING_KEY_PREFIX) and "aparcamientos_en_linea" in key
    ]

    assert linea_keys

    linea_place = place_from_redis_hash(fake_redis.hgetall(linea_keys[0]))

    assert linea_place.sourceDataset == "aparcamientos_en_linea"
    assert linea_place.geometryType == ParkingGeometryType.LINE_STRING


def test_run_import_dir_handles_unknown_filename_gracefully(tmp_path: Path, fake_redis):
    _write_geojson(tmp_path, "experimento_2030.geojson", [
        _point(-6.37, 39.47, {"NOMBRE": "Origen"}),
    ])

    summary = run_import_dir(tmp_path, fake_redis)

    assert summary["imported"] == 1

    by_dataset = {source["sourceDataset"]: source for source in summary["sources"]}

    assert "experimento_2030" in by_dataset

    summary2 = run_import_dir(tmp_path, fake_redis)

    assert summary2["imported"] == 1


def test_run_import_dir_skips_corrupt_files(tmp_path: Path, fake_redis):
    _write_geojson(tmp_path, "parking_bicis.geojson", [
        _point(-6.37, 39.47, {"NOMBRE_VIA": "COLON"}),
    ])
    (tmp_path / "roto.geojson").write_text("{not json", encoding="utf-8")

    summary = run_import_dir(tmp_path, fake_redis)

    assert summary["imported"] == 1
    assert len(summary["files_skipped"]) == 1
    assert summary["files_skipped"][0]["filename"] == "roto.geojson"
    assert "error" in summary["files_skipped"][0]


def test_run_import_dir_is_idempotent(tmp_path: Path, fake_redis):
    _write_geojson(tmp_path, "aparcamientos_en_linea.geojson", [
        _line_string([[-6.40, 39.47], [-6.41, 39.48]]),
        _line_string([[-6.42, 39.49], [-6.43, 39.50]]),
    ])

    first = run_import_dir(tmp_path, fake_redis)

    assert first["imported"] == 2

    keys_after_first = sorted(
        key for key in fake_redis.hashes if key.startswith(PARKING_KEY_PREFIX)
    )

    second = run_import_dir(tmp_path, fake_redis)

    assert second["imported"] == 2

    keys_after_second = sorted(
        key for key in fake_redis.hashes if key.startswith(PARKING_KEY_PREFIX)
    )

    assert keys_after_first == keys_after_second


def test_run_import_dir_with_empty_directory_returns_zero(tmp_path: Path, fake_redis):
    summary = run_import_dir(tmp_path, fake_redis)

    assert summary["status"] == "ok"
    assert summary["imported"] == 0
    assert summary["skipped"] == 0
    assert summary["files_processed"] == 0


def test_imported_features_round_trip_through_redis_hash(tmp_path: Path, fake_redis):
    _write_geojson(tmp_path, "movilidad_reducida.geojson", [
        _point(-6.37, 39.47, {
            "CODIGO_VIA": 4143,
            "NOMBRE_VIA": "DEL FERROCARRIL",
            "TIPO_VIA": "AVDA",
            "BARRIO": "ESTACION",
            "URL_FOTO": "https://sig.caceres.es/foto.jpg",
        }),
    ])
    _write_geojson(tmp_path, "aparcamientos_en_linea.geojson", [
        _line_string([[-6.40, 39.47], [-6.41, 39.48], [-6.42, 39.49]]),
    ])

    run_import_dir(tmp_path, fake_redis)

    for key in fake_redis.hashes:
        if not key.startswith(PARKING_KEY_PREFIX):
            continue

        place = place_from_redis_hash(fake_redis.hgetall(key))

        assert place.id
        assert place.category in ParkingCategory
        assert place.vehicleType in ParkingVehicleType
        assert place.regulation in ParkingRegulation
        assert place.geometryType in ParkingGeometryType
        assert 39.0 < place.latitude < 40.0
        assert -7.0 < place.longitude < -6.0


def test_explicit_property_overrides_profile_default():
    feat = _point(-6.37, 39.47, {"category": "blue_zone"})

    place = feature_to_place(
        feat,
        source=SOURCE_REGISTRY["parking_bicis.geojson"],
    )

    assert place is not None
    assert place.category == ParkingCategory.BLUE_ZONE