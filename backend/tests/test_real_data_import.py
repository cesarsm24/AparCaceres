"""Regresiones contra los GeoJSON reales incluidos en el repositorio.

Validan que los conteos por dataset, la unicidad de ids y el tratamiento de
geometrías especiales permanecen estables al importar los datos reales.
"""

from __future__ import annotations

from app.core.config import DATA_DIR, PARKING_KEY_PREFIX
from app.infra.redis.importer import run_import_dir

EXPECTED_DATASET_COUNTS = {
    "aparcamientos": 24,
    "parkings": 8,
    "aparcamientos_en_bateria": 1424,
    "aparcamientos_en_linea": 4779,
    "zona_azul": 101,
    "carga_descarga": 73,
    "movilidad_reducida": 743,
    "parking_bicis": 68,
    "parking_motos_areas": 48,
    "parking_motos_puntos": 46,
}


def test_real_geojson_import_counts_and_ids_are_stable(fake_redis):
    summary = run_import_dir(DATA_DIR, fake_redis)

    assert summary["status"] == "ok"
    assert summary["files_processed"] == 10
    assert summary["files_skipped"] == []
    assert summary["imported"] == sum(EXPECTED_DATASET_COUNTS.values()) == 7314
    assert summary["skipped"] == 0
    assert summary["ids_disambiguated"] == 11

    by_dataset = {row["sourceDataset"]: row for row in summary["sources"]}

    assert set(by_dataset) == set(EXPECTED_DATASET_COUNTS)

    for dataset, expected_count in EXPECTED_DATASET_COUNTS.items():
        assert by_dataset[dataset]["imported"] == expected_count
        assert by_dataset[dataset]["skipped"] == 0

    ids = [
        data["id"]
        for key, data in fake_redis.hashes.items()
        if key.startswith(PARKING_KEY_PREFIX)
    ]

    assert len(ids) == 7314
    assert len(ids) == len(set(ids))


def test_real_geojson_import_includes_carga_descarga_multipolygons(fake_redis):
    run_import_dir(DATA_DIR, fake_redis)

    carga = [
        data
        for data in fake_redis.hashes.values()
        if data.get("sourceDataset") == "carga_descarga"
    ]

    assert len(carga) == EXPECTED_DATASET_COUNTS["carga_descarga"]
    assert {data["geometryType"] for data in carga} == {"polygon"}