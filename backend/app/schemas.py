"""Schemas Pydantic alineados 1:1 con el cliente Flutter.

Wire format:
- Campos en camelCase.
- Enums como string en snake_case (ver `app/enums.py`).
- Optional[...] = `null` (no cadena vacía).
- Geometrías GeoJSON `[lon, lat]`.

Toda la API de lectura (`/parkings`, `/parkings/nearby`, `/parkings/{id}`,
`/parkings/categories`) y el importador serializan a través de estos modelos.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ParkingCategory,
    ParkingGeometryType,
    ParkingRegulation,
    ParkingVehicleType,
)
from .normalization import (
    coerce_category,
    coerce_geometry_type,
    coerce_line_string,
    coerce_optional_int,
    coerce_optional_str,
    coerce_polygon,
    coerce_regulation,
    coerce_vehicle_type,
)


# ============================================================
# Contrato móvil — lo que consume Flutter
# ============================================================

class ParkingPlaceOut(BaseModel):
    """Contrato de salida alineado 1:1 con `ParkingPlace.fromJson` en Flutter.

    Reglas de normalización aplicadas en `mode='before'` (vienen del wire):
    - Enums desconocidos / vacíos / `None` -> default del enum (no error).
    - Strings opcionales vacíos / whitespace -> `None`.
    - `totalSpaces` admite int, float (redondeado), string parseable o `None`.

    Reglas en `mode='after'` (dependencia entre campos):
    - POINT: se descarta cualquier `coordinates` que llegue (ruido).
    - POLYGON: `coordinates` se valida como lista de anillos (cada anillo ≥3 pts).
    - LINE_STRING: `coordinates` se valida como lista de puntos.
    """

    # extra='ignore' porque el dataset GeoJSON tiene muchos campos que no nos interesan.
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str = ""
    category: ParkingCategory = ParkingCategory.PARKING
    vehicleType: ParkingVehicleType = ParkingVehicleType.CAR
    regulation: ParkingRegulation = ParkingRegulation.FREE
    geometryType: ParkingGeometryType = ParkingGeometryType.POINT
    latitude: float
    longitude: float

    # Forma de `coordinates` según `geometryType`:
    #   POINT       -> None
    #   POLYGON     -> list[list[tuple[float, float]]]   (rings de [lon, lat])
    #   LINE_STRING -> list[tuple[float, float]]         (puntos [lon, lat])
    # Lo declaramos como `list` genérico aquí y normalizamos en model_validator.
    coordinates: Optional[list] = None

    totalSpaces: Optional[int] = None
    streetName: Optional[str] = None
    streetType: Optional[str] = None
    district: Optional[str] = None
    neighborhood: Optional[str] = None
    sourceDataset: Optional[str] = None
    imageUrl: Optional[str] = None
    urlFicha: Optional[str] = None
    urlVia: Optional[str] = None
    management: Optional[str] = None

    # ---------- Normalización per-campo ----------

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v):
        # `name` no es opcional pero permitimos `None` -> "" (Flutter hace lo mismo).
        return "" if v is None else str(v)

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v):
        return coerce_category(v)

    @field_validator("vehicleType", mode="before")
    @classmethod
    def _normalize_vehicle_type(cls, v):
        return coerce_vehicle_type(v)

    @field_validator("regulation", mode="before")
    @classmethod
    def _normalize_regulation(cls, v):
        return coerce_regulation(v)

    @field_validator("geometryType", mode="before")
    @classmethod
    def _normalize_geometry_type(cls, v):
        return coerce_geometry_type(v)

    @field_validator(
        "streetName",
        "streetType",
        "district",
        "neighborhood",
        "sourceDataset",
        "imageUrl",
        "urlFicha",
        "urlVia",
        "management",
        mode="before",
    )
    @classmethod
    def _normalize_optional_str(cls, v):
        return coerce_optional_str(v)

    @field_validator("totalSpaces", mode="before")
    @classmethod
    def _normalize_total_spaces(cls, v):
        return coerce_optional_int(v)

    # ---------- Normalización dependiente del tipo geométrico ----------

    @model_validator(mode="after")
    def _normalize_coordinates(self):
        if self.geometryType == ParkingGeometryType.POINT:
            # POINT no usa el campo coordinates; lo limpiamos para no enviar ruido.
            self.coordinates = None
        elif self.geometryType == ParkingGeometryType.POLYGON:
            self.coordinates = coerce_polygon(self.coordinates)
        elif self.geometryType == ParkingGeometryType.LINE_STRING:
            self.coordinates = coerce_line_string(self.coordinates)
        return self


class ParkingPlaceNearbyOut(ParkingPlaceOut):
    """`ParkingPlaceOut` + distancia al punto de búsqueda, en metros.

    Flutter actualmente ignora `distanceMeters` (su `ParkingPlace.fromJson` no
    lo lee), pero exponerlo es útil para depurar y para futuras pantallas
    de "ordenar por distancia" sin recálculo en cliente.
    """

    distanceMeters: float = Field(..., description="Distancia en metros desde el punto consultado")


# ============================================================
# Filtros de consulta — espejo de `ParkingQuery` en Flutter.
# Se usarán cuando se refactoricen los endpoints en PRs posteriores.
# ============================================================

class ParkingQueryFilters(BaseModel):
    """Filtros de `/parkings/nearby` alineados con `ParkingQuery` en Flutter.

    No se usa todavía en ningún endpoint; queda definido para que el cliente
    Flutter ya pueda formar la query y para tener un lugar único donde validar.
    """

    model_config = ConfigDict(extra="forbid")

    lat: Optional[float] = None
    lng: Optional[float] = None
    radiusMeters: int = Field(1000, ge=0)
    vehicleTypes: list[ParkingVehicleType] = Field(default_factory=list)
    categories: list[ParkingCategory] = Field(default_factory=list)
    regulations: list[ParkingRegulation] = Field(default_factory=list)
    minSpaces: int = Field(0, ge=0)
