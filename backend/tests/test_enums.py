"""Verifica que los `.value` de los enums son IDÉNTICOS a los strings que parsea Flutter.

Si un test de este archivo falla, casi seguro que se ha roto el wire contract
y el cliente móvil va a empezar a recibir defaults silenciosamente.
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


# ---------- Wire values (deben coincidir con los `case '...' =>` de Flutter) ----------

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
    assert {c.value for c in ParkingCategory} == expected


def test_vehicle_type_wire_values():
    assert {v.value for v in ParkingVehicleType} == {"car", "motorbike", "bike"}


def test_regulation_wire_values():
    assert {r.value for r in ParkingRegulation} == {
        "free",
        "paid",
        "blue_zone",
        "loading",
        "reserved",
    }


def test_geometry_type_wire_values():
    assert {g.value for g in ParkingGeometryType} == {"point", "polygon", "line_string"}


# ---------- Mapeo lenient (wire string -> miembro del enum) ----------

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


# ---------- Serialización ----------

def test_enums_serialize_to_wire_strings_via_json():
    """El cliente Flutter recibe los enums como string crudo, no como 'ParkingCategory.PAID_PARKING'."""
    assert json.dumps(ParkingCategory.PAID_PARKING) == '"paid_parking"'
    assert json.dumps(ParkingGeometryType.LINE_STRING) == '"line_string"'
