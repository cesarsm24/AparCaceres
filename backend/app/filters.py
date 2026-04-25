"""Filtros y búsqueda accent-insensitive sobre `ParkingPlaceOut`.

Replica la semántica de `mobile/lib/features/search/data/parking_search.dart`
y de `LocalParkingRepository.getNearby` (filtros por enum + minSpaces) para que
los endpoints devuelvan exactamente el mismo subset que el cliente Flutter
calculaba en local.

Funciones puras: no tocan Redis ni FastAPI -> reutilizables desde tests.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .enums import ParkingCategory, ParkingRegulation, ParkingVehicleType
from .schemas import ParkingPlaceOut

# Mapa de translación accent-insensitive equivalente al `_normalize` de Dart.
# Incluye mayúsculas y minúsculas para no tener que normalizar dos veces.
_ACCENT_TRANSLATION = str.maketrans(
    "áàäâéèëêíìïîóòöôúùüûñçÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛÑÇ",
    "aaaaeeeeiiiioooouuuuncAAAAEEEEIIIIOOOOUUUUNC",
)

# Campos sobre los que aplica la búsqueda libre `q`. Mismo orden que el
# `haystacks` de Flutter para que el comportamiento sea idéntico.
_SEARCHABLE_FIELDS: tuple[str, ...] = (
    "name",
    "streetName",
    "streetType",
    "district",
    "neighborhood",
)


def normalize_for_search(value: str) -> str:
    """Lowercase + strip + sustitución de acentos. Espejo de `_normalize` (Dart).

    Devuelve `""` para entradas vacías (no levanta).
    """
    if not value:
        return ""
    return value.translate(_ACCENT_TRANSLATION).lower().strip()


def place_matches_query(place: ParkingPlaceOut, normalized_q: str) -> bool:
    """`True` si `normalized_q` aparece en cualquiera de los campos buscables.

    `normalized_q` debe venir ya normalizado (el llamador llama a
    `normalize_for_search` una sola vez por request, no una vez por place).
    """
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
    """Aplica todos los filtros del contrato en un único pase.

    Cada parámetro es opcional y vacío significa "no filtrar por esto".
    Mantiene el orden de entrada (importante para `/nearby`, donde Redis ya
    devuelve los resultados ordenados por distancia).
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
