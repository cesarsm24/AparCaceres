"""Búsqueda y filtros puros sobre aparcamientos.

Replica la semántica de filtrado del cliente móvil para que los endpoints
devuelvan el mismo subconjunto que espera la interfaz. No accede a Redis ni a
FastAPI, por lo que puede reutilizarse directamente en tests.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .enums import ParkingCategory, ParkingRegulation, ParkingVehicleType
from .schemas import ParkingPlaceOut

_ACCENT_TRANSLATION = str.maketrans(
    "áàäâéèëêíìïîóòöôúùüûñçÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛÑÇ",
    "aaaaeeeeiiiioooouuuuncAAAAEEEEIIIIOOOOUUUUNC",
)

_SEARCHABLE_FIELDS: tuple[str, ...] = (
    "name",
    "streetName",
    "streetType",
    "district",
    "neighborhood",
)


def normalize_for_search(value: str) -> str:
    """Normaliza texto para comparaciones insensibles a mayúsculas y acentos."""
    if not value:
        return ""

    return value.translate(_ACCENT_TRANSLATION).lower().strip()


def place_matches_query(place: ParkingPlaceOut, normalized_q: str) -> bool:
    """Indica si una consulta normalizada aparece en los campos buscables."""
    if not normalized_q:
        return True

    for field_name in _SEARCHABLE_FIELDS:
        value = getattr(place, field_name, None)
        if not value:
            continue

        if normalized_q in normalize_for_search(value):
            return True

    return False


def apply_filters(
    places: Iterable[ParkingPlaceOut],
    *,
    ids: Optional[set[str]] = None,
    normalized_q: Optional[str] = None,
    vehicle_types: Optional[set[ParkingVehicleType]] = None,
    categories: Optional[set[ParkingCategory]] = None,
    regulations: Optional[set[ParkingRegulation]] = None,
    min_spaces: int = 0,
) -> list[ParkingPlaceOut]:
    """Aplica los filtros del contrato en un único recorrido.

    Los filtros vacíos se ignoran. El orden de entrada se conserva para no
    alterar resultados ya ordenados por otra capa, como las búsquedas cercanas.
    """
    out: list[ParkingPlaceOut] = []

    for place in places:
        if ids is not None and place.id not in ids:
            continue

        if vehicle_types and place.vehicleType not in vehicle_types:
            continue

        if categories and place.category not in categories:
            continue

        if regulations and place.regulation not in regulations:
            continue

        if min_spaces > 0 and (
            place.totalSpaces is None or place.totalSpaces < min_spaces
        ):
            continue

        if normalized_q and not place_matches_query(place, normalized_q):
            continue

        out.append(place)

    return out