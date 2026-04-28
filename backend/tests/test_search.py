"""Tests unitarios de la capa RediSearch."""

from __future__ import annotations

from app.infra.redis.search import _ft_nearby_rows
from app.schemas import ParkingPlaceNearbyOut

# Hashes simulados que devuelve `FT.AGGREGATE … LOAD *` para cada miembro:
# misma estructura que los hashes `parking:{id}` reales, más el campo
# computado `distance` que añade el `APPLY geodistance(...)`.
_HASH_1 = [
    "id", "aparcamientos:1",
    "name", "Plaza 1",
    "category", "parking",
    "vehicleType", "car",
    "regulation", "free",
    "geometryType", "point",
    "latitude", "39.47",
    "longitude", "-6.37",
    "location", "-6.37,39.47",
    "distance", "12.5",
]
_HASH_2 = [
    "id", "aparcamientos:2",
    "name", "Plaza 2",
    "category", "parking",
    "vehicleType", "car",
    "regulation", "free",
    "geometryType", "point",
    "latitude", "39.471",
    "longitude", "-6.371",
    "location", "-6.371,39.471",
    "distance", "25.0",
]


class _FakeRediSearch:
    def __init__(self) -> None:
        self.commands: list[tuple] = []

    def execute_command(self, *args):
        self.commands.append(args)
        if args[:2] == ("FT.INFO", "idx:parkings_search"):
            return ["index_name", "idx:parkings_search"]
        if args[:2] == ("FT.AGGREGATE", "idx:parkings_search"):
            return [2, _HASH_1, _HASH_2]
        raise AssertionError(f"comando inesperado: {args!r}")


def test_ft_nearby_rows_uses_aggregate_distance_sorting():
    """`_ft_nearby_rows` debe pedir `LOAD *` con `APPLY geodistance(...)` y
    `SORTBY @distance ASC`, y devolver `ParkingPlaceNearbyOut` directamente
    (sin necesidad de un HGETALL adicional)."""
    redis = _FakeRediSearch()

    total, rows = _ft_nearby_rows(
        redis,
        query="@location:[-6.37 39.47 1000 m]",
        lng=-6.37,
        lat=39.47,
        offset=5,
        limit=10,
    )

    assert total == 2
    assert len(rows) == 2
    assert all(isinstance(r, ParkingPlaceNearbyOut) for r in rows)
    assert [r.id for r in rows] == ["aparcamientos:1", "aparcamientos:2"]
    assert [r.distanceMeters for r in rows] == [12.5, 25.0]
    # El campo computado `distance` se elimina antes de hidratar el modelo,
    # así que el contrato móvil expone solo `distanceMeters`.
    assert all(r.name for r in rows)

    aggregate = redis.commands[-1]
    assert aggregate[:3] == (
        "FT.AGGREGATE",
        "idx:parkings_search",
        "@location:[-6.37 39.47 1000 m]",
    )
    # `LOAD *` es lo que evita el round-trip extra HGETALL.
    load_idx = aggregate.index("LOAD")
    assert aggregate[load_idx + 1] == "*"
    assert "APPLY" in aggregate
    assert "geodistance(@location,-6.37,39.47)" in aggregate
    assert "SORTBY" in aggregate
    assert "@distance" in aggregate
    assert "MAX" in aggregate
    assert aggregate[aggregate.index("MAX") + 1] == 15
    assert aggregate[-5:] == ("LIMIT", 5, 10, "DIALECT", "2")
