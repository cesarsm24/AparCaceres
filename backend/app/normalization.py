"""Helpers puros de normalización wire -> tipos del dominio backend.

Replican el parsing lenient que hace Flutter en `ParkingPlace.fromJson`:
- Valores desconocidos o vacíos de enum caen al default, no lanzan excepción.
- Cadenas vacías o whitespace en campos opcionales se traducen a `None`.
- Enteros opcionales admiten num, float, string parseable o `None`.
- Coordenadas en formato GeoJSON `[lon, lat]` (¡ojo al orden!).
- Polígonos descartan anillos con menos de 3 puntos (matches Flutter `ring.length >= 3`).

Mantener estas funciones SIN dependencias de Pydantic ni de FastAPI para que
sean reutilizables desde el importador y desde los tests.
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

# Tipos de coordenada usados en el wire (cada coord = [lon, lat]).
Coordinate = tuple[float, float]
LineString = list[Coordinate]
Polygon = list[LineString]


# ---------- Enums (wire string -> miembro del enum) ----------

def coerce_enum(value: object, enum_cls: Type[E], default: E) -> E:
    """Devuelve el miembro del enum correspondiente a `value`; si no hay match, `default`.

    Equivalente a los `switch (value) { case 'x' => ...; _ => default }` de Dart.
    """
    if value is None or value == "":
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def coerce_category(value: object) -> ParkingCategory:
    return coerce_enum(value, ParkingCategory, ParkingCategory.PARKING)


def coerce_vehicle_type(value: object) -> ParkingVehicleType:
    return coerce_enum(value, ParkingVehicleType, ParkingVehicleType.CAR)


def coerce_regulation(value: object) -> ParkingRegulation:
    return coerce_enum(value, ParkingRegulation, ParkingRegulation.FREE)


def coerce_geometry_type(value: object) -> ParkingGeometryType:
    return coerce_enum(value, ParkingGeometryType, ParkingGeometryType.POINT)


# ---------- Escalares opcionales ----------

def coerce_optional_str(value: object) -> Optional[str]:
    """`None` para valores vacíos/whitespace; si no, `str(value).strip()`.

    Flutter consume `null` como "campo ausente", así que no queremos emitir `""`.
    """
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def coerce_optional_int(value: object) -> Optional[int]:
    """Convierte a int si es posible; `None` para valores vacíos o no parseables.

    Refleja `_toNullableInt` en Dart: acepta int, float (redondeado), string
    parseable (entero o float), `None`.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        # bool es subclase de int en Python; preservamos el comportamiento True->1 / False->0.
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


# ---------- Geometrías ----------

def coerce_coordinate(value: object) -> Optional[Coordinate]:
    """Valida una coordenada wire `[lon, lat]`. Devuelve `None` si es inválida.

    Sólo mira los dos primeros elementos del array (igual que Dart), así que un
    `[lon, lat, alt]` también se acepta como `(lon, lat)`.
    """
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def coerce_line_string(coords: object) -> LineString:
    """Lista de coordenadas válidas; descarta silenciosamente las inválidas."""
    if not isinstance(coords, (list, tuple)):
        return []
    out: LineString = []
    for c in coords:
        parsed = coerce_coordinate(c)
        if parsed is not None:
            out.append(parsed)
    return out


def coerce_polygon(coords: object) -> Polygon:
    """Lista de anillos válidos. Cada anillo debe tener ≥ 3 puntos para ser válido.

    Los anillos degenerados (0, 1 ó 2 puntos) se descartan — un polígono real
    necesita al menos un triángulo.
    """
    if not isinstance(coords, (list, tuple)):
        return []
    return [ring for ring in (coerce_line_string(r) for r in coords) if len(ring) >= 3]
