"""Tests del contrato público de modelos de aparcamiento.

Verifican defaults, serialización wire, normalización de opcionales,
tratamiento de geometrías y extensión del modelo para resultados cercanos.
"""

import json

from app.enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from app.schemas import ParkingPlaceNearbyOut, ParkingPlaceOut, ParkingQueryFilters


def test_minimal_valid_input_applies_defaults():
    place = ParkingPlaceOut(id="abc", latitude=39.47, longitude=-6.37)

    assert place.id == "abc"
    assert place.name == ""
    assert place.category == ParkingCategory.PARKING
    assert place.vehicleType == ParkingVehicleType.CAR
    assert place.regulation == ParkingRegulation.FREE
    assert place.geometryType == ParkingGeometryType.POINT
    assert place.coordinates is None

    for field in (
        place.streetName,
        place.streetType,
        place.district,
        place.neighborhood,
        place.sourceDataset,
        place.imageUrl,
        place.urlFicha,
        place.urlVia,
        place.management,
        place.totalSpaces,
    ):
        assert field is None


def test_unknown_enum_values_fall_back_to_defaults():
    place = ParkingPlaceOut(
        id="x",
        latitude=0.0,
        longitude=0.0,
        category="gibberish",
        vehicleType="alien",
        regulation="plasma",
        geometryType="cube",
    )

    assert place.category == ParkingCategory.PARKING
    assert place.vehicleType == ParkingVehicleType.CAR
    assert place.regulation == ParkingRegulation.FREE
    assert place.geometryType == ParkingGeometryType.POINT


def test_name_none_becomes_empty_string():
    place = ParkingPlaceOut(id="x", latitude=0, longitude=0, name=None)

    assert place.name == ""


def test_enum_serialization_matches_wire_values():
    place = ParkingPlaceOut(
        id="x",
        latitude=0.0,
        longitude=0.0,
        category="paid_parking",
        vehicleType="bike",
        regulation="blue_zone",
        geometryType="polygon",
        coordinates=[[[0, 0], [1, 0], [1, 1], [0, 0]]],
    )

    data = json.loads(place.model_dump_json())

    assert data["category"] == "paid_parking"
    assert data["vehicleType"] == "bike"
    assert data["regulation"] == "blue_zone"
    assert data["geometryType"] == "polygon"


def test_point_geometry_strips_coordinates_even_if_provided():
    place = ParkingPlaceOut(
        id="x",
        latitude=1.0,
        longitude=2.0,
        geometryType="point",
        coordinates=[[1, 2], [3, 4]],
    )

    assert place.coordinates is None


def test_polygon_keeps_valid_rings_only():
    rings = [
        [[0, 0], [1, 0], [1, 1], [0, 0]],
        [[5, 5], [6, 5]],
        [[7, 7], [8, 7], [8, 8]],
    ]

    place = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        geometryType="polygon",
        coordinates=rings,
    )

    assert len(place.coordinates) == 2
    assert place.coordinates[0] == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
    assert place.coordinates[1] == [(7.0, 7.0), (8.0, 7.0), (8.0, 8.0)]


def test_polygon_with_no_valid_rings_becomes_empty_list():
    place = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        geometryType="polygon",
        coordinates=[[[0, 0], [1, 0]]],
    )

    assert place.coordinates == []


def test_line_string_keeps_lon_lat_order():
    coords = [[-6.37, 39.47], [-6.38, 39.48], [-6.39, 39.49]]

    place = ParkingPlaceOut(
        id="x",
        latitude=39.47,
        longitude=-6.37,
        geometryType="line_string",
        coordinates=coords,
    )

    assert place.coordinates == [(-6.37, 39.47), (-6.38, 39.48), (-6.39, 39.49)]


def test_line_string_drops_invalid_coordinates_silently():
    coords = [[-6.37, 39.47], None, [1], "broken", [9, 9]]

    place = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        geometryType="line_string",
        coordinates=coords,
    )

    assert place.coordinates == [(-6.37, 39.47), (9.0, 9.0)]


def test_optional_strings_normalize_whitespace_to_none():
    place = ParkingPlaceOut(
        id="x",
        latitude=0,
        longitude=0,
        streetName="  ",
        streetType="",
        district=None,
        neighborhood="Centro",
        management="\t\n",
    )

    assert place.streetName is None
    assert place.streetType is None
    assert place.district is None
    assert place.neighborhood == "Centro"
    assert place.management is None


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
        place = ParkingPlaceOut(id="x", latitude=0, longitude=0, totalSpaces=raw)

        assert place.totalSpaces == expected, f"raw={raw!r}"


def test_optional_fields_serialize_as_null_when_missing():
    place = ParkingPlaceOut(id="x", latitude=0, longitude=0)
    data = json.loads(place.model_dump_json())

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


def test_nearby_extends_base_and_adds_distance():
    nearby = ParkingPlaceNearbyOut(
        id="x",
        latitude=39.47,
        longitude=-6.37,
        distanceMeters=123.4,
    )

    data = json.loads(nearby.model_dump_json())

    assert data["distanceMeters"] == 123.4
    assert data["geometryType"] == "point"
    assert data["coordinates"] is None
    assert data["category"] == "parking"


def test_query_filters_defaults():
    filters = ParkingQueryFilters()

    assert filters.lat is None
    assert filters.lng is None
    assert filters.radiusMeters == 1000
    assert filters.minSpaces == 0
    assert filters.vehicleTypes == []
    assert filters.categories == []
    assert filters.regulations == []


def test_query_filters_accept_lists_of_enum_wire_values():
    filters = ParkingQueryFilters(
        lat=39.47,
        lng=-6.37,
        radiusMeters=500,
        vehicleTypes=["car", "bike"],
        categories=["paid_parking", "blue_zone"],
        regulations=["paid"],
        minSpaces=5,
    )

    assert filters.vehicleTypes == [ParkingVehicleType.CAR, ParkingVehicleType.BIKE]
    assert filters.categories == [ParkingCategory.PAID_PARKING, ParkingCategory.BLUE_ZONE]
    assert filters.regulations == [ParkingRegulation.PAID]
    assert filters.minSpaces == 5