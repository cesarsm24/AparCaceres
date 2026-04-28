"""Modelos Pydantic del contrato público de aparcamientos.

Define el formato JSON expuesto por la API y consumido por el cliente móvil:
campos en camelCase, enumeraciones serializadas como cadenas y valores
opcionales representados como `null`. También centraliza la normalización
tolerante de datos de catálogo antes de devolverlos o persistirlos.
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


class ParkingPlaceOut(BaseModel):
    """Aparcamiento serializado según el contrato de lectura público.

    Los valores incompletos o desconocidos se normalizan de forma tolerante
    para evitar que registros parciales del catálogo rompan las respuestas.
    Las coordenadas se ajustan según `geometryType`.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str = ""
    category: ParkingCategory = ParkingCategory.PARKING
    vehicleType: ParkingVehicleType = ParkingVehicleType.CAR
    regulation: ParkingRegulation = ParkingRegulation.FREE
    geometryType: ParkingGeometryType = ParkingGeometryType.POINT
    latitude: float
    longitude: float
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

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v):
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

    @model_validator(mode="after")
    def _normalize_coordinates(self):
        """Normaliza la geometría al formato esperado por el tipo declarado."""
        if self.geometryType == ParkingGeometryType.POINT:
            self.coordinates = None
        elif self.geometryType == ParkingGeometryType.POLYGON:
            self.coordinates = coerce_polygon(self.coordinates)
        elif self.geometryType == ParkingGeometryType.LINE_STRING:
            self.coordinates = coerce_line_string(self.coordinates)

        return self


class ParkingPlaceNearbyOut(ParkingPlaceOut):
    """Aparcamiento cercano con distancia calculada desde el punto consultado."""

    distanceMeters: float = Field(
        ...,
        description="Distancia en metros desde el punto consultado.",
    )


class ParkingFacetsOut(BaseModel):
    """Conteos agregados del catálogo para filtros de cliente."""

    total: int = 0
    categories: dict[str, int] = Field(default_factory=dict)
    vehicleTypes: dict[str, int] = Field(default_factory=dict)
    regulations: dict[str, int] = Field(default_factory=dict)
    datasets: dict[str, int] = Field(default_factory=dict)


class ParkingPlacesEnvelopeOut(BaseModel):
    """Respuesta paginada de listados de aparcamientos."""

    items: list[ParkingPlaceOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0
    truncated: bool = False
    facets: Optional[ParkingFacetsOut] = None


class ParkingPlacesNearbyEnvelopeOut(BaseModel):
    """Respuesta paginada de búsquedas de aparcamientos cercanos."""

    items: list[ParkingPlaceNearbyOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0
    truncated: bool = False
    facets: Optional[ParkingFacetsOut] = None


class FavoriteAdded(BaseModel):
    """Resultado de añadir un aparcamiento a favoritos.

    `created` permite distinguir una creación real de una repetición
    idempotente. `addedAt` conserva la marca temporal persistida.
    """

    id: str = Field(..., description="Id del aparcamiento favoritado.")
    addedAt: str = Field(
        ...,
        description="Marca temporal ISO 8601 UTC de entrada en favoritos.",
    )
    created: bool = Field(
        ...,
        description="Indica si la entrada se ha creado en esta operación.",
    )


class FavoriteRemoved(BaseModel):
    """Resultado de eliminar un aparcamiento de favoritos."""

    id: str = Field(..., description="Id del aparcamiento sobre el que se actuó.")
    removed: bool = Field(
        ...,
        description="Indica si existía una entrada de favorito y se eliminó.",
    )


class ParkingQueryFilters(BaseModel):
    """Filtros de consulta compartidos para búsquedas de aparcamientos."""

    model_config = ConfigDict(extra="forbid")

    lat: Optional[float] = None
    lng: Optional[float] = None
    radiusMeters: int = Field(1000, ge=0)
    vehicleTypes: list[ParkingVehicleType] = Field(default_factory=list)
    categories: list[ParkingCategory] = Field(default_factory=list)
    regulations: list[ParkingRegulation] = Field(default_factory=list)
    minSpaces: int = Field(0, ge=0)