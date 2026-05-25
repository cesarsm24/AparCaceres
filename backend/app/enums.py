"""Enumeraciones públicas del contrato de aparcamientos.

Define los valores serializados que consume el cliente móvil. Cada valor debe
mantenerse alineado con el modelo de dominio de Flutter para preservar la
compatibilidad del contrato JSON.
"""

from enum import Enum


class ParkingCategory(str, Enum):
    """Categoría funcional del aparcamiento."""

    PARKING = "parking"
    PAID_PARKING = "paid_parking"
    STREET_LINE = "street_line"
    STREET_BATTERY = "street_battery"
    BLUE_ZONE = "blue_zone"
    ACCESSIBLE = "accessible"
    MOTORBIKE = "motorbike"
    BICYCLE = "bicycle"
    LOADING = "loading"


class ParkingVehicleType(str, Enum):
    """Tipo principal de vehículo admitido."""

    CAR = "car"
    MOTORBIKE = "motorbike"
    BIKE = "bike"


class ParkingRegulation(str, Enum):
    """Régimen de uso asociado al aparcamiento."""

    FREE = "free"
    PAID = "paid"
    BLUE_ZONE = "blue_zone"
    LOADING = "loading"
    RESERVED = "reserved"


class ParkingGeometryType(str, Enum):
    """Geometría usada para representar la ubicación."""

    POINT = "point"
    POLYGON = "polygon"
    LINE_STRING = "line_string"