"""Tests del contrato móvil (`ParkingPlaceOut`, `ParkingPlaceNearbyOut`).

Comprueban que el schema:
- Aplica defaults para enums vacíos / desconocidos.
- Serializa enums como wire strings (snake_case).
- Maneja las 3 geometrías (point / polygon / line_string).
- Trata opcionales como `null` cuando llegan vacíos.
- `ParkingPlaceNearbyOut` extiende correctamente al base.
"""

import json

from app.enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from app.schemas import ParkingPlaceNearbyOut, ParkingPlaceOut, ParkingQueryFilters


# ---------- Defaults / inicialización mínima ----------

def test_minimal_valid_input_applies_defaults():
    p = ParkingPlaceOut(id="abc", latitude=39.47, longitude=-6.37)
    assert p.id == "abc"
    assert p.name == ""
    assert p.category == ParkingCategory.PARKING
    assert p.vehicleType == ParkingVehicleType.CAR
    assert p.regulation == ParkingRegulation.FREE
    assert p.geometryType == ParkingGeometryType.POINT
    assert p.coordinates is None
    # Los opcionales deben ser None, no "".
    for field in (
        p.streetName,
        p.streetType,
        p.district,
        p.neighborhood,
        p.sourceDataset,
        p.imageUrl,
        p.urlFicha,
        p.urlVia,
        p.management,
        p.totalSpaces,
    ):
        assert field is None


def test_unknown_enum_values_fall_back_to_defaults():
    p = ParkingPlaceOut(
        id="x",
        latitude=0.0,
        longitude=0.0,
        category="gibberish",
        vehicleType="alien",
        regulation="plasma",
        geometryType="cube",
    )
    assert p.category == ParkingCategory.PARKING
    assert p.vehicleType == ParkingVehicleType.CAR
    assert p.regulation == ParkingRegulation.FREE
    assert p.geometryType == ParkingGeometryType.POINT


def test_name_none_becomes_empty_string():
    p = ParkingPlaceOut(id="x", latitude=0, longitude=0, name=None)
    assert p.name == ""


# ---------- Serialización de enums en JSON ----------

def test_enum_serialization_matches_wire_values():
    p = ParkingPlaceOut(
        id="x",
        latitude=0.0,
        longitude=0.0,
        category="paid_parking",
        vehicleType="bike",
        regulation="blue_zone",
        geometryType="polygon",
        coordinates=[[[0, 0], [1, 0], [1, 1], [0, 0]]],
    )
    data = json.loads(p.model_dump_json())
    assert data["category"] == "paid_parking"
    assert data["vehicleType"] == "bike"
    assert data["regulation"] == "blue_zone"
    assert data["geometryType"] == "polygon"


# ---------- Geometría: POINT ----------

def test_point_geometry_strips_coordinates_even_if_provided():
    p = ParkingPlaceOut(
        id="x",
        latitude=1.0,
        longitude=2.0,
        geometryType="point",
        coordinates=[[1, 2], [3, 4]],  # ruido para POINT
    )
    assert p.coordinates is None


# ---------- Geometría: POLYGON ----------

def test_polygon_keeps_valid_rings_only():
    rings = [
        [[0, 0], [1, 0], [1, 1], [0, 0]],   # válido (4 pts)
        [[5, 5], [6, 5]],                    # inválido (2 pts) -> descartar
        [[7, 7], [8, 7], [8, 8]],            # válido (3 pts)
    ]
    p = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        geometryType="polygon",
        coordinates=rings,
    )
    assert len(p.coordinates) == 2
    assert p.coordinates[0] == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
    assert p.coordinates[1] == [(7.0, 7.0), (8.0, 7.0), (8.0, 8.0)]


def test_polygon_with_no_valid_rings_becomes_empty_list():
    p = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        geometryType="polygon",
        coordinates=[[[0, 0], [1, 0]]],  # < 3 pts
    )
    assert p.coordinates == []


# ---------- Geometría: LINE_STRING ----------

def test_line_string_keeps_lon_lat_order():
    coords = [[-6.37, 39.47], [-6.38, 39.48], [-6.39, 39.49]]
    p = ParkingPlaceOut(
        id="x",
        latitude=39.47,
        longitude=-6.37,
        geometryType="line_string",
        coordinates=coords,
    )
    assert p.coordinates == [(-6.37, 39.47), (-6.38, 39.48), (-6.39, 39.49)]


def test_line_string_drops_invalid_coordinates_silently():
    coords = [[-6.37, 39.47], None, [1], "broken", [9, 9]]
    p = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        geometryType="line_string",
        coordinates=coords,
    )
    assert p.coordinates == [(-6.37, 39.47), (9.0, 9.0)]


# ---------- Opcionales ----------

def test_optional_strings_normalize_whitespace_to_none():
    p = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        streetName="  ",
        streetType="",
        district=None,
        neighborhood="Centro",
        management="\t\n",
    )
    assert p.streetName is None
    assert p.streetType is None
    assert p.district is None
    assert p.neighborhood == "Centro"
    assert p.management is None


def test_total_spaces_coerces_int_from_strings_floats_and_none():
    cases = [
        ("42", 42),
        (42, 42),
        (42.8, 43),
        ("12.3", 12),
        (None, None),
        ("", None),
        ("abc", None),
    ]
    for raw, expected in cases:
        p = ParkingPlaceOut(id="x", latitude=0, longitude=0, totalSpaces=raw)
        assert p.totalSpaces == expected, f"raw={raw!r}"


def test_optional_fields_serialize_as_null_when_missing():
    p = ParkingPlaceOut(id="x", latitude=0, longitude=0)
    data = json.loads(p.model_dump_json())
    for field in (
        "streetName",
        "streetType",
        "district",
        "neighborhood",
        "sourceDataset",
        "imageUrl",
        "urlFicha",
        "urlVia",
        "management",
        "totalSpaces",
    ):
        assert data[field] is None, f"{field} debería ser null en wire"


# ---------- ParkingPlaceNearbyOut ----------

def test_nearby_extends_base_and_adds_distance():
    n = ParkingPlaceNearbyOut(
        id="x",
        latitude=39.47,
        longitude=-6.37,
        distanceMeters=123.4,
    )
    data = json.loads(n.model_dump_json())
    assert data["distanceMeters"] == 123.4
    # Mantiene todos los campos del base.
    assert data["geometryType"] == "point"
    assert data["coordinates"] is None
    assert data["category"] == "parking"


# ---------- ParkingQueryFilters ----------

def test_query_filters_defaults():
    f = ParkingQueryFilters()
    assert f.lat is None
    assert f.lng is None
    assert f.radiusMeters == 1000
    assert f.minSpaces == 0
    assert f.vehicleTypes == []
    assert f.categories == []
    assert f.regulations == []


def test_query_filters_accept_lists_of_enum_wire_values():
    f = ParkingQueryFilters(
        lat=39.47,
        lng=-6.37,
        radiusMeters=500,
        vehicleTypes=["car", "bike"],
        categories=["paid_parking", "blue_zone"],
        regulations=["paid"],
        minSpaces=5,
    )
    assert f.vehicleTypes == [ParkingVehicleType.CAR, ParkingVehicleType.BIKE]
    assert f.categories == [ParkingCategory.PAID_PARKING, ParkingCategory.BLUE_ZONE]
    assert f.regulations == [ParkingRegulation.PAID]
    assert f.minSpaces == 5
