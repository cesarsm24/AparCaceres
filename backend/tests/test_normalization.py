"""Tests de normalización de valores wire.

Verifican conversiones tolerantes de enums, escalares opcionales y geometrías
GeoJSON usadas por el contrato de aparcamientos.
"""

import pytest

from app.enums import ParkingCategory
from app.normalization import (
    coerce_coordinate,
    coerce_enum,
    coerce_line_string,
    coerce_optional_int,
    coerce_optional_str,
    coerce_polygon,
)


def test_coerce_enum_returns_default_on_unknown():
    assert (
        coerce_enum("???", ParkingCategory, ParkingCategory.PARKING)
        is ParkingCategory.PARKING
    )


def test_coerce_enum_returns_member_on_known():
    assert (
        coerce_enum("paid_parking", ParkingCategory, ParkingCategory.PARKING)
        is ParkingCategory.PAID_PARKING
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("\t\n", None),
        ("Cáceres", "Cáceres"),
        ("  hola  ", "hola"),
        (123, "123"),
    ],
)
def test_coerce_optional_str(value, expected):
    assert coerce_optional_str(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        (42, 42),
        (42.6, 43),
        (42.4, 42),
        ("42", 42),
        ("  7  ", 7),
        ("12.7", 13),
        ("abc", None),
        (True, 1),
        (False, 0),
    ],
)
def test_coerce_optional_int(value, expected):
    assert coerce_optional_int(value) == expected


def test_coerce_coordinate_valid():
    assert coerce_coordinate([-6.37, 39.47]) == (-6.37, 39.47)
    assert coerce_coordinate(["1", "2"]) == (1.0, 2.0)
    assert coerce_coordinate([1, 2, 3]) == (1.0, 2.0)
    assert coerce_coordinate((10, 20)) == (10.0, 20.0)


def test_coerce_coordinate_invalid():
    assert coerce_coordinate(None) is None
    assert coerce_coordinate([1]) is None
    assert coerce_coordinate("not a list") is None
    assert coerce_coordinate([1, "bad"]) is None
    assert coerce_coordinate({}) is None


def test_coerce_line_string_filters_invalid_silently():
    raw = [[-6.37, 39.47], None, [1], [2, 3], "broken", [9, 9]]

    assert coerce_line_string(raw) == [(-6.37, 39.47), (2.0, 3.0), (9.0, 9.0)]


def test_coerce_line_string_non_list_yields_empty():
    assert coerce_line_string(None) == []
    assert coerce_line_string("nope") == []
    assert coerce_line_string({}) == []


def test_coerce_polygon_keeps_only_rings_with_three_or_more_points():
    raw = [
        [[0, 0], [1, 0], [1, 1], [0, 0]],
        [[0, 0], [1, 0]],
        [[0, 0], [1, 0], [1, 1]],
        [],
    ]

    polygon = coerce_polygon(raw)

    assert len(polygon) == 2
    assert polygon[0] == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
    assert polygon[1] == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]


def test_coerce_polygon_non_list_yields_empty():
    assert coerce_polygon(None) == []
    assert coerce_polygon("nope") == []