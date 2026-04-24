from pydantic import BaseModel, Field


class Parking(BaseModel):
    """Metadatos de un aparcamiento (corresponde al hash `parking:{id}` en Redis)."""

    id: str
    nombre: str
    clase: str
    direccion: str = ""
    nucleo: str = ""
    url: str = ""
    lat: float
    lon: float


class ParkingNearby(Parking):
    """Aparcamiento + distancia desde el punto de búsqueda (en metros)."""

    distancia_metros: float = Field(..., description="Distancia al punto consultado, en metros")
