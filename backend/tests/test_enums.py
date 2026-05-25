"""Tests del contrato wire de enumeraciones.

Garantizan que los valores serializados coinciden con los esperados por el
cliente móvil y que la normalización tolerante aplica los defaults previstos.
"""

import json

import pytest

from app.enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from app.normalization import (
    coerce_category,
    coerce_geometry_type,
    coerce_regulation,
    coerce_vehicle_type,
)


def test_category_wire_values():
    expected = {
        "parking",
        "paid_parking",
        "street_line",
        "street_battery",
        "blue_zone",
        "accessible",
        "motorbike",
        "bicycle",
        "loading",
    }

    assert {category.value for category in ParkingCategory} == expected


def test_vehicle_type_wire_values():
    assert {vehicle.value for vehicle in ParkingVehicleType} == {"car", "motorbike", "bike"}


def test_regulation_wire_values():
    assert {regulation.value for regulation in ParkingRegulation} == {
        "free",
        "paid",
        "blue_zone",
        "loading",
        "reserved",
    }


def test_geometry_type_wire_values():
    assert {geometry.value for geometry in ParkingGeometryType} == {"point", "polygon", "line_string"}


@pytest.mark.parametrize(
    "wire, expected",
    [
        ("parking", ParkingCategory.PARKING),
        ("paid_parking", ParkingCategory.PAID_PARKING),
        ("street_line", ParkingCategory.STREET_LINE),
        ("street_battery", ParkingCategory.STREET_BATTERY),
        ("blue_zone", ParkingCategory.BLUE_ZONE),
        ("accessible", ParkingCategory.ACCESSIBLE),
        ("motorbike", ParkingCategory.MOTORBIKE),
        ("bicycle", ParkingCategory.BICYCLE),
        ("loading", ParkingCategory.LOADING),
    ],
)
def test_coerce_category_known_values(wire, expected):
    assert coerce_category(wire) is expected


@pytest.mark.parametrize("bad", [None, "", "unknown_value", 123, [], {}])
def test_coerce_category_unknown_falls_back_to_default(bad):
    assert coerce_category(bad) is ParkingCategory.PARKING


def test_coerce_vehicle_type_default_and_match():
    assert coerce_vehicle_type(None) is ParkingVehicleType.CAR
    assert coerce_vehicle_type("") is ParkingVehicleType.CAR
    assert coerce_vehicle_type("motorbike") is ParkingVehicleType.MOTORBIKE
    assert coerce_vehicle_type("bike") is ParkingVehicleType.BIKE
    assert coerce_vehicle_type("???") is ParkingVehicleType.CAR


def test_coerce_regulation_default_and_match():
    assert coerce_regulation(None) is ParkingRegulation.FREE
    assert coerce_regulation("paid") is ParkingRegulation.PAID
    assert coerce_regulation("blue_zone") is ParkingRegulation.BLUE_ZONE
    assert coerce_regulation("reserved") is ParkingRegulation.RESERVED
    assert coerce_regulation("xyz") is ParkingRegulation.FREE


def test_coerce_geometry_type_default_and_match():
    assert coerce_geometry_type(None) is ParkingGeometryType.POINT
    assert coerce_geometry_type("polygon") is ParkingGeometryType.POLYGON
    assert coerce_geometry_type("line_string") is ParkingGeometryType.LINE_STRING
    assert coerce_geometry_type("blob") is ParkingGeometryType.POINT


def test_enums_serialize_to_wire_strings_via_json():
    assert json.dumps(ParkingCategory.PAID_PARKING) == '"paid_parking"'
    assert json.dumps(ParkingGeometryType.LINE_STRING) == '"line_string"'