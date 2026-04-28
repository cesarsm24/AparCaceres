"""Tests del importador multi-fichero.

Cubre las garantías que añade el procesamiento por lotes:

- Procesa todos los `*.geojson` del directorio de datos.
- Tolera claves heterogéneas entre ficheros (`CODIGO_VIA` vs `CODIGOVIA`,
  `NOMBREVIA` vs `NOMBRE_VIA`, etc.) sin fallar.
- Infiere `category`/`vehicleType`/`regulation` del nombre del fichero cuando
  el feature no los aporta.
- Genera ids deterministas y únicos cuando no hay `mslink` (`{prefix}-{hash}`).
- Clasifica URLs heterogéneas (`URL_FOTO` -> imageUrl, `fichacalle.php` -> urlVia,
  `mslink=` -> urlFicha, `*.JPG` -> imageUrl).
- Devuelve un resumen con desglose por `sourceDataset`.

Construye datasets sintéticos en directorios temporales (`tmp_path`), así no
dependemos del estado de `data/` al ejecutar pytest.
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

# ============================================================
# Helpers de construcción de GeoJSON sintético
# ============================================================

def _write_geojson(directory: Path, filename: str, features: list[dict]) -> Path:
    """Escribe un FeatureCollection mínimo y devuelve la ruta."""
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


# ============================================================
# Registry / profile_for
# ============================================================

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
    # Defaults seguros (no rompemos el contrato si llega un dataset nuevo).
    assert profile.default_category == ParkingCategory.PARKING
    assert profile.default_vehicle_type == ParkingVehicleType.CAR
    assert profile.default_regulation == ParkingRegulation.FREE
    assert profile.source_dataset == "ataques_marcianos"


# ============================================================
# Inferencia desde el filename — properties vacías
# ============================================================

def test_feature_with_empty_properties_inherits_profile_defaults():
    """`carga_descarga.geojson` y `aparcamientos_en_linea.geojson` no siempre
    incluyen `category`/`regulation`. Con profile producen un place
    completamente válido y el contrato lo guarda sin huecos."""
    feat = _line_string([
        [-6.401, 39.477],
        [-6.402, 39.478],
        [-6.403, 39.479],
    ])
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]

    place = feature_to_place(feat, source=profile)
    assert place is not None
    # Todos los enums caen en el profile, no en el default genérico del enum.
    assert place.category == profile.default_category
    assert place.vehicleType == profile.default_vehicle_type
    assert place.regulation == profile.default_regulation
    assert place.sourceDataset == profile.source_dataset
    # Sin name explícito se usa el fallback del profile.
    assert place.name == profile.fallback_name
    # Geometría preservada para el contrato.
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
        feat, source=SOURCE_REGISTRY["parking_motos_puntos.geojson"]
    )
    assert place is not None
    assert place.vehicleType == ParkingVehicleType.MOTORBIKE
    assert place.category == ParkingCategory.MOTORBIKE


def test_carga_descarga_profile_overrides_misleading_tipo_field():
    """`carga_descarga.geojson` trae `TIPO=ZONA AZUL` en algunos features,
    pero el filename indica que son plazas de carga/descarga. El profile manda
    sobre la heurística textual del feature."""
    feat = _polygon([
        [-6.38, 39.47], [-6.38, 39.48], [-6.37, 39.48], [-6.38, 39.47]
    ])
    feat["properties"] = {"TIPO": "ZONA AZUL", "PLAZAS": "2"}
    place = feature_to_place(feat, source=SOURCE_REGISTRY["carga_descarga.geojson"])
    assert place is not None
    assert place.category == ParkingCategory.LOADING
    assert place.regulation == ParkingRegulation.LOADING


# ============================================================
# Claves heterogéneas (CODIGO_VIA / CODIGOVIA / NOMBREVIA / NOMBRE_VIA / ...)
# ============================================================

def test_feature_with_codigovia_single_word_does_not_crash():
    """`aparcamientos_en_bateria.geojson` usa `CODIGOVIA`, sin underscore."""
    feat = _polygon([
        [-6.38, 39.47], [-6.38, 39.48], [-6.37, 39.48], [-6.38, 39.47]
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
        feat, source=SOURCE_REGISTRY["aparcamientos_en_bateria.geojson"]
    )
    assert place is not None
    assert place.streetName == "DEL FERROCARRIL"
    assert place.streetType == "AVDA"
    assert place.totalSpaces == 8
    # `fichacalle.php` clasifica como `urlVia` (no `urlFicha`).
    assert place.urlVia and "fichacalle.php" in place.urlVia
    assert place.urlFicha is None


def test_feature_with_codigo_via_underscore_variant_normalizes_same():
    """`movilidad_reducida.geojson` usa `CODIGO_VIA` y `NOMBRE_VIA`."""
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
        feat, source=SOURCE_REGISTRY["movilidad_reducida.geojson"]
    )
    assert place is not None
    assert place.streetName == "DEL FERROCARRIL"
    assert place.streetType == "AVDA"
    assert place.neighborhood == "ESTACION"
    assert place.district == "OESTE"
    # URL_FOTO -> imageUrl, URL_FICHA -> urlFicha, URL_VIA -> urlVia.
    assert place.imageUrl == "https://sig.caceres.es/foto.jpg"
    assert place.urlFicha and "fichatoponimia.php" in place.urlFicha
    assert place.urlVia and "fichacalle.php" in place.urlVia
    assert place.management == "AYUNTAMIENTO"


def test_parkings_uses_denominaci_truncated_shapefile_field():
    """`parkings.geojson` usa `DENOMINACI` (10 chars de shapefile) en vez de NOMBRE."""
    feat = _point(-6.374084, 39.475736)
    feat["properties"] = {
        "CLASE": "PARKING",
        "DENOMINACI": "Obispo Galarza",
        "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1882",
    }
    place = feature_to_place(feat, source=SOURCE_REGISTRY["parkings.geojson"])
    assert place is not None
    assert place.name == "Obispo Galarza"
    # parkings.geojson mapea a paid_parking + paid (parkings públicos de pago).
    assert place.category == ParkingCategory.PAID_PARKING
    assert place.regulation == ParkingRegulation.PAID
    # Mslink prevalece sobre el id-hash del profile, namespaced por dataset.
    assert place.id == "parkings:1882"


# ============================================================
# URL classification
# ============================================================

def test_url_classification_routes_image_url_to_imageurl():
    feat = _point(-6.37, 39.47)
    feat["properties"] = {
        "URL": "https://sig.caceres.es/fotosOriginales/PARKING_BICIS/134_1.JPG",
    }
    place = feature_to_place(feat, source=SOURCE_REGISTRY["parking_bicis.geojson"])
    assert place is not None
    assert place.imageUrl is not None and place.imageUrl.endswith("134_1.JPG")
    # Una URL de imagen no debe mancharse en urlFicha/urlVia.
    assert place.urlFicha is None
    assert place.urlVia is None


def test_url_classification_routes_fichacalle_to_urlvia():
    feat = _polygon([
        [-6.38, 39.47], [-6.38, 39.48], [-6.37, 39.48], [-6.38, 39.47]
    ])
    feat["properties"] = {
        "URL": "https://sig.caceres.es/serweb/fichasig/fichacalle.php?codigo=42",
    }
    place = feature_to_place(feat, source=SOURCE_REGISTRY["zona_azul.geojson"])
    assert place is not None
    assert place.urlVia and "fichacalle.php" in place.urlVia
    assert place.urlFicha is None


# ============================================================
# IDs deterministas / fallback
# ============================================================

def test_derive_stable_id_falls_back_to_hash_when_source_present():
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]
    coords = [[-6.40, 39.47], [-6.41, 39.48]]
    parking_id = derive_stable_id(
        {},  # properties vacías
        source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )
    assert parking_id is not None
    # Formato: `{sourceDataset}:{sha256[:20]}`.
    namespace, fp = parking_id.split(":", 1)
    assert namespace == "aparcamientos_en_linea"
    assert len(fp) == 20


def test_hash_id_is_deterministic_across_calls():
    """Reimportar el mismo dataset debe producir los mismos ids → no duplica."""
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]
    coords = [[-6.40, 39.47], [-6.41, 39.48]]
    a = derive_stable_id({}, source=profile,
                         geometry_type=ParkingGeometryType.LINE_STRING,
                         raw_coords=coords)
    b = derive_stable_id({}, source=profile,
                         geometry_type=ParkingGeometryType.LINE_STRING,
                         raw_coords=coords)
    assert a == b


def test_hash_ids_differ_between_distinct_features_in_same_source():
    profile = SOURCE_REGISTRY["aparcamientos_en_linea.geojson"]
    a = derive_stable_id(
        {}, source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=[[-6.40, 39.47], [-6.41, 39.48]],
    )
    b = derive_stable_id(
        {}, source=profile,
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=[[-6.50, 39.50], [-6.51, 39.51]],
    )
    assert a != b


def test_hash_ids_namespace_by_profile_prefix():
    """Mismo geometryType + coords pero ficheros distintos → ids distintos."""
    coords = [[-6.40, 39.47], [-6.41, 39.48]]
    a = derive_stable_id(
        {},
        source=SOURCE_REGISTRY["aparcamientos_en_bateria.geojson"],
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )
    b = derive_stable_id(
        {},
        source=SOURCE_REGISTRY["aparcamientos_en_linea.geojson"],
        geometry_type=ParkingGeometryType.LINE_STRING,
        raw_coords=coords,
    )
    assert a is not None and b is not None
    assert a.split(":", 1)[0] == "aparcamientos_en_bateria"
    assert b.split(":", 1)[0] == "aparcamientos_en_linea"
    assert a != b


# ============================================================
# discover_geojson_files
# ============================================================

def test_discover_geojson_files_lists_only_geojson_sorted(tmp_path: Path):
    _write_geojson(tmp_path, "b.geojson", [])
    _write_geojson(tmp_path, "a.geojson", [])
    (tmp_path / "leeme.txt").write_text("ignorame", encoding="utf-8")
    files = discover_geojson_files(tmp_path)
    assert [p.name for p in files] == ["a.geojson", "b.geojson"]


def test_discover_geojson_files_returns_empty_for_missing_dir(tmp_path: Path):
    assert discover_geojson_files(tmp_path / "no-existe") == []


# ============================================================
# run_import_sources / run_import_dir orquestación
# ============================================================

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

    # Desglose por sourceDataset.
    by_dataset = {s["sourceDataset"]: s for s in summary["sources"]}
    assert by_dataset["aparcamientos_en_linea"]["imported"] == 2
    assert by_dataset["parking_bicis"]["imported"] == 1

    # En Redis: 3 hashes canónicos `parking:{id}`.
    assert sum(1 for k in fake_redis.hashes if k.startswith(PARKING_KEY_PREFIX)) == 3


def test_run_import_dir_processes_all_files_in_directory(tmp_path: Path, fake_redis):
    # Tres ficheros con perfiles distintos.
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

    # Comprobamos que cada fichero contribuyó con el contrato esperado.
    by_dataset = {s["sourceDataset"]: s for s in summary["sources"]}
    assert by_dataset["parking_bicis"]["imported"] == 1
    assert by_dataset["aparcamientos_en_linea"]["imported"] == 2
    assert by_dataset["zona_azul"]["imported"] == 1

    # Y verificamos los enums por hash en Redis (al menos uno por dataset).
    linea_keys = [
        k for k in fake_redis.hashes
        if k.startswith(PARKING_KEY_PREFIX) and "aparcamientos_en_linea" in k
    ]
    assert linea_keys
    linea_place = place_from_redis_hash(fake_redis.hgetall(linea_keys[0]))
    assert linea_place.sourceDataset == "aparcamientos_en_linea"
    assert linea_place.geometryType == ParkingGeometryType.LINE_STRING


def test_run_import_dir_handles_unknown_filename_gracefully(tmp_path: Path, fake_redis):
    """Un GeoJSON con nombre desconocido recibe el profile genérico (defaults
    seguros) y se importa con id hash-based, sin abortar."""
    _write_geojson(tmp_path, "experimento_2030.geojson", [
        _point(-6.37, 39.47, {"NOMBRE": "Origen"}),
    ])
    summary = run_import_dir(tmp_path, fake_redis)
    assert summary["imported"] == 1
    # `sourceDataset` arriba es el stem del filename para trazabilidad.
    by_dataset = {s["sourceDataset"]: s for s in summary["sources"]}
    assert "experimento_2030" in by_dataset
    # Idempotencia: reimportar no añade duplicados (id estable por hash).
    summary2 = run_import_dir(tmp_path, fake_redis)
    assert summary2["imported"] == 1


def test_run_import_dir_skips_corrupt_files(tmp_path: Path, fake_redis):
    """Un fichero con JSON inválido se loggea y se reporta en `files_skipped`
    sin abortar el resto."""
    _write_geojson(tmp_path, "parking_bicis.geojson", [
        _point(-6.37, 39.47, {"NOMBRE_VIA": "COLON"}),
    ])
    (tmp_path / "roto.geojson").write_text("{not json", encoding="utf-8")

    summary = run_import_dir(tmp_path, fake_redis)
    # El bici se importa; el roto se reporta.
    assert summary["imported"] == 1
    assert len(summary["files_skipped"]) == 1
    assert summary["files_skipped"][0]["filename"] == "roto.geojson"
    assert "error" in summary["files_skipped"][0]


def test_run_import_dir_is_idempotent(tmp_path: Path, fake_redis):
    """Reimportar dos veces deja Redis con el mismo contenido (no duplica)."""
    _write_geojson(tmp_path, "aparcamientos_en_linea.geojson", [
        _line_string([[-6.40, 39.47], [-6.41, 39.48]]),
        _line_string([[-6.42, 39.49], [-6.43, 39.50]]),
    ])

    first = run_import_dir(tmp_path, fake_redis)
    assert first["imported"] == 2

    keys_after_first = sorted(
        k for k in fake_redis.hashes if k.startswith(PARKING_KEY_PREFIX)
    )

    second = run_import_dir(tmp_path, fake_redis)
    assert second["imported"] == 2

    keys_after_second = sorted(
        k for k in fake_redis.hashes if k.startswith(PARKING_KEY_PREFIX)
    )
    # Los ids estables → mismas claves entre ejecuciones.
    assert keys_after_first == keys_after_second


def test_run_import_dir_with_empty_directory_returns_zero(tmp_path: Path, fake_redis):
    summary = run_import_dir(tmp_path, fake_redis)
    assert summary["status"] == "ok"
    assert summary["imported"] == 0
    assert summary["skipped"] == 0
    assert summary["files_processed"] == 0


# ============================================================
# Conformidad estricta con el contrato móvil
# ============================================================

def test_imported_features_round_trip_through_redis_hash(tmp_path: Path, fake_redis):
    """Sea cual sea el origen, el hash en Redis se reconstruye en un
    `ParkingPlaceOut` válido (esto es lo que consume Flutter)."""
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
        # Contrato no rompible: enums presentes y geometría válida.
        assert place.id
        assert place.category in ParkingCategory
        assert place.vehicleType in ParkingVehicleType
        assert place.regulation in ParkingRegulation
        assert place.geometryType in ParkingGeometryType
        # Latitudes plausibles (Cáceres aprox 39.4-39.5, -6.3 a -6.5).
        assert 39.0 < place.latitude < 40.0
        assert -7.0 < place.longitude < -6.0


def test_explicit_property_overrides_profile_default():
    """Si un feature trae `category` explícita, gana sobre el profile."""
    feat = _point(-6.37, 39.47, {"category": "blue_zone"})
    place = feature_to_place(
        feat, source=SOURCE_REGISTRY["parking_bicis.geojson"]
    )
    assert place is not None
    # Explicit > profile.
    assert place.category == ParkingCategory.BLUE_ZONE
