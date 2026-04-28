"""Tests de búsqueda y filtrado puro de aparcamientos.

Verifican normalización textual, coincidencias por consulta libre y composición
de filtros sin alterar el orden de entrada.
"""

from __future__ import annotations

import pytest

from app.enums import ParkingCategory, ParkingRegulation, ParkingVehicleType
from app.filters import apply_filters, normalize_for_search, place_matches_query
from app.schemas import ParkingPlaceOut


def _make(**overrides) -> ParkingPlaceOut:
    """Crea un aparcamiento válido con valores mínimos por defecto."""
    base = dict(id="x", latitude=39.47, longitude=-6.37)
    base.update(overrides)
    return ParkingPlaceOut(**base)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Cáceres", "caceres"),
        ("MAÑANA", "manana"),
        ("  Politécnica  ", "politecnica"),
        ("ÁàÄâÉèËêÍìÏîÓòÖôÚùÜûÑç", "aaaaeeeeiiiioooouuuunc"),
        ("", ""),
        ("sin acentos", "sin acentos"),
    ],
)
def test_normalize_for_search_strips_accents_and_lowercases(raw, expected):
    assert normalize_for_search(raw) == expected


def test_place_matches_query_finds_in_name_accent_insensitive():
    place = _make(name="Politécnica")

    assert place_matches_query(place, normalize_for_search("politec"))


def test_place_matches_query_finds_in_street_name():
    place = _make(name="Algo", streetName="DALIA")

    assert place_matches_query(place, normalize_for_search("dali"))


def test_place_matches_query_finds_in_district_with_accents():
    place = _make(name="x", district="CÁCERES")

    assert place_matches_query(place, normalize_for_search("caceres"))


def test_place_matches_query_finds_in_neighborhood():
    place = _make(name="x", neighborhood="EL JUNQUILLO")

    assert place_matches_query(place, normalize_for_search("junq"))


def test_place_matches_query_returns_false_when_no_field_matches():
    place = _make(name="Plaza Mayor", district="CENTRO")

    assert not place_matches_query(place, normalize_for_search("dalia"))


def test_place_matches_query_empty_query_matches_anything():
    assert place_matches_query(_make(), "")


def test_place_matches_query_ignores_none_fields():
    place = _make(name="hola")

    assert place_matches_query(place, normalize_for_search("hola"))
    assert not place_matches_query(place, normalize_for_search("nada"))


def _dataset() -> list[ParkingPlaceOut]:
    """Devuelve un catálogo sintético con variedad de filtros."""
    return [
        _make(id="a", name="Politécnica", category="parking",
              vehicleType="car", regulation="free"),
        _make(id="b", name="Obispo Galarza", category="paid_parking",
              vehicleType="car", regulation="paid", totalSpaces=120),
        _make(id="c", name="Calle Dalia", category="street_line",
              vehicleType="car", regulation="free", totalSpaces=16),
        _make(id="d", name="Parking Bicis Colon", category="bicycle",
              vehicleType="bike", regulation="reserved", totalSpaces=5),
        _make(id="e", name="Motos Londres", category="motorbike",
              vehicleType="motorbike", regulation="reserved", totalSpaces=15),
    ]


def test_apply_filters_no_filters_returns_all_in_order():
    data = _dataset()

    assert apply_filters(data) == data


def test_apply_filters_by_ids_keeps_only_matching():
    data = _dataset()
    out = apply_filters(data, ids={"a", "c"})

    assert [place.id for place in out] == ["a", "c"]


def test_apply_filters_by_vehicle_type():
    out = apply_filters(_dataset(), vehicle_types={ParkingVehicleType.BIKE})

    assert [place.id for place in out] == ["d"]


def test_apply_filters_by_category_supports_or():
    out = apply_filters(
        _dataset(),
        categories={ParkingCategory.PAID_PARKING, ParkingCategory.MOTORBIKE},
    )

    assert {place.id for place in out} == {"b", "e"}


def test_apply_filters_by_regulation():
    out = apply_filters(_dataset(), regulations={ParkingRegulation.PAID})

    assert [place.id for place in out] == ["b"]


def test_apply_filters_min_spaces_drops_unknown_total_spaces():
    out = apply_filters(_dataset(), min_spaces=10)

    assert {place.id for place in out} == {"b", "c", "e"}


def test_apply_filters_q_search_combines_with_other_filters():
    out = apply_filters(
        _dataset(),
        normalized_q=normalize_for_search("colon"),
        vehicle_types={ParkingVehicleType.BIKE},
    )

    assert [place.id for place in out] == ["d"]


def test_apply_filters_preserves_input_order():
    data = list(reversed(_dataset()))
    out = apply_filters(data, regulations={ParkingRegulation.RESERVED})

    assert [place.id for place in out] == ["e", "d"]