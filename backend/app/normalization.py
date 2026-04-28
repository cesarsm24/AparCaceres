"""Normalización de valores wire al dominio de aparcamientos.

Centraliza conversiones tolerantes para datos procedentes del importador o de
contratos externos. Los valores desconocidos de enumeración se sustituyen por
valores por defecto, los escalares vacíos se tratan como ausentes y las
geometrías inválidas se descartan sin interrumpir el procesamiento.

El módulo no depende de Pydantic ni de FastAPI para poder reutilizarse en
importación, validación y tests.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Type, TypeVar

from .enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)

E = TypeVar("E", bound=Enum)

Coordinate = tuple[float, float]
LineString = list[Coordinate]
Polygon = list[LineString]


def coerce_enum(value: object, enum_cls: Type[E], default: E) -> E:
    """Convierte un valor wire a enum, usando un valor seguro si no coincide."""
    if value is None or value == "":
        return default

    try:
        return enum_cls(value)
    except ValueError:
        return default


def coerce_category(value: object) -> ParkingCategory:
    """Normaliza una categoría de aparcamiento."""
    return coerce_enum(value, ParkingCategory, ParkingCategory.PARKING)


def coerce_vehicle_type(value: object) -> ParkingVehicleType:
    """Normaliza el tipo de vehículo admitido."""
    return coerce_enum(value, ParkingVehicleType, ParkingVehicleType.CAR)


def coerce_regulation(value: object) -> ParkingRegulation:
    """Normaliza el régimen de uso."""
    return coerce_enum(value, ParkingRegulation, ParkingRegulation.FREE)


def coerce_geometry_type(value: object) -> ParkingGeometryType:
    """Normaliza el tipo geométrico."""
    return coerce_enum(value, ParkingGeometryType, ParkingGeometryType.POINT)


def coerce_optional_str(value: object) -> Optional[str]:
    """Convierte valores vacíos en ausencia y conserva texto no vacío."""
    if value is None:
        return None

    s = str(value).strip()
    return s if s else None


def coerce_optional_int(value: object) -> Optional[int]:
    """Convierte enteros opcionales de forma tolerante.

    Acepta enteros, flotantes y cadenas numéricas. Los valores no parseables se
    tratan como ausentes para no bloquear la importación de registros parciales.
    """
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return round(value)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None

        try:
            return int(s)
        except ValueError:
            try:
                return round(float(s))
            except ValueError:
                return None

    return None


def coerce_coordinate(value: object) -> Optional[Coordinate]:
    """Valida una coordenada GeoJSON `[lon, lat]`."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None

    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def coerce_line_string(coords: object) -> LineString:
    """Devuelve las coordenadas válidas de una línea GeoJSON."""
    if not isinstance(coords, (list, tuple)):
        return []

    out: LineString = []
    for coord in coords:
        parsed = coerce_coordinate(coord)
        if parsed is not None:
            out.append(parsed)

    return out


def coerce_polygon(coords: object) -> Polygon:
    """Devuelve los anillos válidos de un polígono GeoJSON.

    Los anillos con menos de tres puntos se descartan porque no representan una
    superficie mínima válida.
    """
    if not isinstance(coords, (list, tuple)):
        return []

    return [
        ring
        for ring in (coerce_line_string(raw_ring) for raw_ring in coords)
        if len(ring) >= 3
    ]