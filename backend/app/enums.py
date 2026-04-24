"""String enums alineados 1:1 con los valores que consume Flutter.

Referencia autoritativa: `mobile/lib/features/parking/domain/parking_place.dart`,
métodos `_categoryFromWire`, `_vehicleTypeFromWire`, `_regulationFromWire`,
`_geometryTypeFromWire`. Cada `.value` de abajo DEBE coincidir con uno de los
`case 'xxx' =>` de esos switches.

Heredamos de `str, Enum` para que:
- `json.dumps(ParkingCategory.PARKING)` emita la cadena cruda.
- Pydantic las serialice directamente como string sin `use_enum_values`.
- Las comparaciones contra literales (`my_cat == "paid_parking"`) funcionen.
"""

from enum import Enum


class ParkingCategory(str, Enum):
    """Tipos de aparcamiento. Default cuando el valor wire es desconocido: PARKING."""

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
    """Vehículos admitidos. Default: CAR."""

    CAR = "car"
    MOTORBIKE = "motorbike"
    BIKE = "bike"


class ParkingRegulation(str, Enum):
    """Régimen de uso del aparcamiento. Default: FREE."""

    FREE = "free"
    PAID = "paid"
    BLUE_ZONE = "blue_zone"
    LOADING = "loading"
    RESERVED = "reserved"


class ParkingGeometryType(str, Enum):
    """Tipo geométrico de la ubicación del aparcamiento. Default: POINT."""

    POINT = "point"
    POLYGON = "polygon"
    LINE_STRING = "line_string"
