"""Tests unitarios de la capa RediSearch."""

from __future__ import annotations

from app.search import _ft_nearby_rows


class _FakeRediSearch:
    def __init__(self) -> None:
        self.commands: list[tuple] = []

    def execute_command(self, *args):
        self.commands.append(args)
        if args[:2] == ("FT.INFO", "idx:parkings_search"):
            return ["index_name", "idx:parkings_search"]
        if args[:2] == ("FT.AGGREGATE", "idx:parkings_search"):
            return [
                2,
                ["id", "aparcamientos:1", "distance", "12.5"],
                ["id", "aparcamientos:2", "distance", "25.0"],
            ]
        raise AssertionError(f"comando inesperado: {args!r}")


def test_ft_nearby_rows_uses_aggregate_distance_sorting():
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
    assert rows == [("aparcamientos:1", 12.5), ("aparcamientos:2", 25.0)]

    aggregate = redis.commands[-1]
    assert aggregate[:3] == ("FT.AGGREGATE", "idx:parkings_search", "@location:[-6.37 39.47 1000 m]")
    assert "APPLY" in aggregate
    assert "geodistance(@location,-6.37,39.47)" in aggregate
    assert "SORTBY" in aggregate
    assert "@distance" in aggregate
    assert "MAX" in aggregate
    assert aggregate[aggregate.index("MAX") + 1] == 15
    assert aggregate[-5:] == ("LIMIT", 5, 10, "DIALECT", "2")
