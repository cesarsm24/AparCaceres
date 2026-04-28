"""Fixtures y dobles de Redis compartidos por la suite de tests.

Define una implementación en memoria del subconjunto de Redis usado por la
aplicación y adaptadores síncronos/asíncronos para inyectarla en FastAPI. Esto
permite probar routers e importador sin depender de Redis Stack en CI.
"""

from __future__ import annotations

import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("METRICS_ENABLED", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5000")
os.environ.setdefault("IMPORT_TOKEN", "test-import-token")
os.environ.setdefault("FAVORITES_SECRET", "test-secret-do-not-leak")

from typing import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from redis.exceptions import ResponseError  # noqa: E402


class FakeRedis:
    """Implementación en memoria del subconjunto de `redis-py` usado en tests."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.search_indices: set[str] = set()

    def ping(self) -> bool:
        return True

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def hset(self, key: str, mapping: dict | None = None) -> int:
        if not mapping:
            return 0

        bucket = self.hashes.setdefault(key, {})
        added = 0

        for k, v in mapping.items():
            sk = str(k)
            if sk not in bucket:
                added += 1
            bucket[sk] = str(v)

        return added

    def delete(self, *keys: str) -> int:
        removed = 0

        for key in keys:
            for store in (self.hashes, self.strings, self.zsets):
                if key in store:
                    del store[key]
                    removed += 1

        return removed

    def exists(self, *keys: str) -> int:
        found = 0

        for key in keys:
            for store in (self.hashes, self.strings, self.zsets):
                if key in store:
                    found += 1
                    break

        return found

    def scan_iter(self, match: str | None = None) -> Iterator[str]:
        all_keys = (
            list(self.hashes.keys())
            + list(self.strings.keys())
            + list(self.zsets.keys())
        )

        if match is None:
            yield from all_keys
            return

        if match.endswith("*"):
            prefix = match[:-1]
            for key in all_keys:
                if key.startswith(prefix):
                    yield key
            return

        for key in all_keys:
            if key == match:
                yield key

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.strings[key] = str(value)
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.strings[key] = str(value)
        return True

    def get(self, key: str) -> str | None:
        return self.strings.get(key)

    def incr(self, key: str, amount: int = 1) -> int:
        """Incrementa un valor entero inicializado implícitamente a cero."""
        current = int(self.strings.get(key, "0") or "0")
        new_value = current + int(amount)
        self.strings[key] = str(new_value)
        return new_value

    def execute_command(self, *args):
        """Ejecuta el subconjunto de comandos RediSearch requerido por los tests."""
        if not args:
            raise AssertionError("comando vacío")

        command = str(args[0]).upper()
        if command == "FT.CREATE":
            return self._ft_create(*args[1:])
        if command == "FT.DROPINDEX":
            return self._ft_dropindex(*args[1:])
        if command == "FT.INFO":
            return self._ft_info(*args[1:])
        if command == "FT.SEARCH":
            return self._ft_search(*args[1:])
        if command == "FT.AGGREGATE":
            return self._ft_aggregate(*args[1:])

        raise AssertionError(f"comando inesperado: {args!r}")

    def zscore(self, key: str, member: str) -> float | None:
        zset = self.zsets.get(key)
        if zset is not None:
            return zset.get(member)

        return None

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        bucket = self.zsets.setdefault(key, {})
        added = 0

        for member, score in mapping.items():
            if member not in bucket:
                added += 1
            bucket[str(member)] = float(score)

        return added

    def zrem(self, key: str, *members: str) -> int:
        bucket = self.zsets.get(key)
        if not bucket:
            return 0

        removed = 0

        for member in members:
            if member in bucket:
                del bucket[member]
                removed += 1

        if not bucket:
            del self.zsets[key]

        return removed

    def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        """Devuelve miembros ordenados por score descendente.

        En empates se aplica orden lexicográfico descendente para emular Redis.
        """
        bucket = self.zsets.get(key, {})
        if not bucket:
            return []

        items = sorted(bucket.items(), key=lambda item: item[0], reverse=True)
        items = sorted(items, key=lambda item: item[1], reverse=True)
        members = [member for member, _ in items]

        if end == -1:
            return members[start:]

        return members[start : end + 1]

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        """Elimina miembros por rango ascendente de score."""
        bucket = self.zsets.get(key)
        if not bucket:
            return 0

        ordered = sorted(bucket.items(), key=lambda item: (item[1], item[0]))
        total = len(ordered)
        normalized_start = start if start >= 0 else max(total + start, 0)
        normalized_stop = stop if stop >= 0 else total + stop

        if normalized_start > normalized_stop or normalized_start >= total:
            return 0

        normalized_stop = min(normalized_stop, total - 1)
        victims = [
            member
            for member, _ in ordered[normalized_start : normalized_stop + 1]
        ]

        for member in victims:
            bucket.pop(member, None)

        if not bucket:
            del self.zsets[key]

        return len(victims)

    def expire(self, key: str, seconds: int) -> bool:
        for store in (self.hashes, self.strings, self.zsets):
            if key in store:
                return True

        return False

    def rename(self, src: str, dst: str) -> bool:
        for store in (self.hashes, self.strings, self.zsets):
            if src in store:
                store[dst] = store.pop(src)
                return True

        raise KeyError(f"no such key: {src}")

    def _ft_create(self, name: str, *_args):
        self.search_indices.add(str(name))
        return "OK"

    def _ft_dropindex(self, name: str, *_args):
        name = str(name)
        if name not in self.search_indices:
            raise ResponseError("Unknown index name")

        self.search_indices.remove(name)
        return "OK"

    def _ft_info(self, name: str):
        name = str(name)
        if name not in self.search_indices:
            raise ResponseError("Unknown index name")

        from app.core.config import PARKING_KEY_PREFIX

        num_docs = sum(
            1 for key in self.hashes if key.startswith(PARKING_KEY_PREFIX)
        )
        return ["index_name", name, "num_docs", num_docs]

    def _ft_search(self, name: str, query: str, *args):
        self._ensure_index(name)
        places = self._filtered_places(query)

        nocontent = any(str(arg).upper() == "NOCONTENT" for arg in args)
        offset, limit = self._extract_limit(args)
        sliced = places[offset : offset + limit]

        out: list = [len(places)]
        for place in sliced:
            out.append(f"parking:{place.id}")
            if not nocontent:
                out.append(self._row_to_list(place.model_dump(mode="json")))

        return out

    def _ft_aggregate(self, name: str, query: str, *args):
        self._ensure_index(name)

        if any(str(arg).upper() == "GROUPBY" for arg in args):
            return self._ft_aggregate_facets(query, *args)

        return self._ft_aggregate_nearby(query, *args)

    def _ft_aggregate_facets(self, query: str, *args):
        places = self._filtered_places(query)
        field = self._extract_groupby_field(args)
        counts: dict[str, int] = {}

        for place in places:
            value = getattr(place, field, None)
            if value is None:
                continue

            if hasattr(value, "value"):
                value = value.value

            key = str(value)
            counts[key] = counts.get(key, 0) + 1

        rows = []
        for key in sorted(counts):
            rows.append([field, key, "count", counts[key]])

        return [len(places), *rows]

    def _ft_aggregate_nearby(self, query: str, *args):
        places = self._filtered_places(query)
        geo = self._extract_geo(query)
        offset, limit = self._extract_limit(args)

        if geo is None:
            rows = [self._row_to_list(place.model_dump(mode="json")) for place in places]
            return [len(places), *rows[offset : offset + limit]]

        lng, lat, radius = geo

        from app.infra.redis.search import _haversine_m

        distances = [
            (place, _haversine_m(lat, lng, place.latitude, place.longitude))
            for place in places
        ]
        distances = [item for item in distances if item[1] <= radius]
        distances.sort(key=lambda item: (item[1], item[0].id))

        rows = []
        for place, distance in distances[offset : offset + limit]:
            data = place.model_dump(mode="json")
            data["distance"] = distance
            rows.append(self._row_to_list(data))

        return [len(distances), *rows]

    def _filtered_places(self, query: str):
        from app.infra.redis.importer import place_from_redis_hash
        from app.infra.redis.search import _filter_places

        places = [
            place_from_redis_hash(data)
            for key, data in self.hashes.items()
            if key.startswith("parking:")
        ]
        params = self._parse_query(query)

        return _filter_places(
            places,
            ids=params["ids"],
            q=params["q"],
            vehicle_types=params["vehicle_types"],
            categories=params["categories"],
            regulations=params["regulations"],
            datasets=params["datasets"],
            min_spaces=params["min_spaces"],
            bounds=params["bounds"],
        )

    def _parse_query(self, query: str) -> dict:
        import re

        tag_pattern = re.compile(r"@(?P<field>\w+):\{(?P<value>[^}]*)\}")
        text_pattern = re.compile(r"@searchText:\((?P<value>[^)]*)\)")
        min_spaces_pattern = re.compile(r"@totalSpaces:\[(?P<min>\d+) \+inf\]")
        lat_pattern = re.compile(r"@latitude:\[(?P<min>[-\d.]+) (?P<max>[-\d.]+)\]")
        lng_pattern = re.compile(r"@longitude:\[(?P<min>[-\d.]+) (?P<max>[-\d.]+)\]")

        ids = vehicle_types = categories = regulations = datasets = None
        q = None
        min_spaces = 0
        bounds = None

        mapping = {
            "id": "ids",
            "vehicleType": "vehicle_types",
            "category": "categories",
            "regulation": "regulations",
            "sourceDataset": "datasets",
        }
        collected: dict[str, list[str]] = {
            "ids": [],
            "vehicle_types": [],
            "categories": [],
            "regulations": [],
            "datasets": [],
        }

        for match in tag_pattern.finditer(query):
            field = match.group("field")
            target = mapping.get(field)
            if target is None:
                continue

            values = [value.replace("\\", "") for value in match.group("value").split("|")]
            collected[target].extend(value for value in values if value)

        if collected["ids"]:
            ids = collected["ids"]
        if collected["vehicle_types"]:
            vehicle_types = collected["vehicle_types"]
        if collected["categories"]:
            categories = collected["categories"]
        if collected["regulations"]:
            regulations = collected["regulations"]
        if collected["datasets"]:
            datasets = collected["datasets"]

        text_match = text_pattern.search(query)
        if text_match:
            tokens = [
                token.rstrip("*")
                for token in text_match.group("value").split()
                if token.rstrip("*")
            ]
            q = " ".join(tokens)

        min_match = min_spaces_pattern.search(query)
        if min_match:
            min_spaces = int(min_match.group("min"))

        lat_match = lat_pattern.search(query)
        lng_match = lng_pattern.search(query)
        if lat_match and lng_match:
            bounds = (
                float(lat_match.group("min")),
                float(lng_match.group("min")),
                float(lat_match.group("max")),
                float(lng_match.group("max")),
            )

        return {
            "ids": ids,
            "q": q,
            "vehicle_types": vehicle_types,
            "categories": categories,
            "regulations": regulations,
            "datasets": datasets,
            "min_spaces": min_spaces,
            "bounds": bounds,
        }

    def _extract_geo(self, query: str):
        import re

        match = re.search(
            r"@location:\[(?P<lng>[-\d.]+) (?P<lat>[-\d.]+) (?P<radius>[-\d.]+) m\]",
            query,
        )
        if not match:
            return None

        return (
            float(match.group("lng")),
            float(match.group("lat")),
            float(match.group("radius")),
        )

    def _extract_groupby_field(self, args) -> str:
        for index, arg in enumerate(args):
            if str(arg).upper() == "GROUPBY" and index + 2 < len(args):
                field = str(args[index + 2])
                return field.lstrip("@")

        raise AssertionError("GROUPBY no encontrado")

    def _extract_limit(self, args) -> tuple[int, int]:
        for index, arg in enumerate(args):
            if str(arg).upper() == "LIMIT" and index + 2 < len(args):
                return int(args[index + 1]), int(args[index + 2])

        return 0, 100

    def _ensure_index(self, name: str) -> None:
        if str(name) not in self.search_indices:
            raise ResponseError("Unknown index name")

    def _row_to_list(self, data: dict) -> list:
        out: list = []

        for key, value in data.items():
            out.extend([str(key), str(value)])

        return out

    def pipeline(self) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    """Pipeline en memoria que ejecuta comandos acumulados en orden."""

    def __init__(self, parent: FakeRedis) -> None:
        self.parent = parent
        self._cmds: list[tuple] = []

    def delete(self, *keys: str) -> "FakePipeline":
        self._cmds.append(("delete", keys))
        return self

    def set(self, key: str, value: str, ex: int | None = None) -> "FakePipeline":
        self._cmds.append(("set", key, value, ex))
        return self

    def hset(self, key: str, mapping: dict | None = None) -> "FakePipeline":
        self._cmds.append(("hset", key, mapping))
        return self

    def hgetall(self, key: str) -> "FakePipeline":
        self._cmds.append(("hgetall", key))
        return self

    def rename(self, src: str, dst: str) -> "FakePipeline":
        self._cmds.append(("rename", src, dst))
        return self

    def execute(self) -> list:
        results = []

        for cmd in self._cmds:
            if cmd[0] == "delete":
                results.append(self.parent.delete(*cmd[1]))
            elif cmd[0] == "set":
                results.append(self.parent.set(cmd[1], cmd[2], ex=cmd[3]))
            elif cmd[0] == "hset":
                results.append(self.parent.hset(cmd[1], mapping=cmd[2]))
            elif cmd[0] == "hgetall":
                results.append(self.parent.hgetall(cmd[1]))
            elif cmd[0] == "rename":
                results.append(self.parent.rename(cmd[1], cmd[2]))

        self._cmds.clear()
        return results


class AsyncFakeRedis:
    """Adaptador asíncrono sobre `FakeRedis` para routers FastAPI."""

    def __init__(self, sync: FakeRedis) -> None:
        self._sync = sync

    async def ping(self) -> bool:
        return self._sync.ping()

    async def hgetall(self, key: str) -> dict[str, str]:
        return self._sync.hgetall(key)

    async def get(self, key: str):
        return self._sync.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        return self._sync.setex(key, ttl, value)

    async def incr(self, key: str, amount: int = 1) -> int:
        return self._sync.incr(key, amount)

    async def exists(self, *keys: str) -> int:
        return self._sync.exists(*keys)

    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        return self._sync.zrevrange(key, start, end)

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        return self._sync.zadd(key, mapping)

    async def zrem(self, key: str, *members: str) -> int:
        return self._sync.zrem(key, *members)

    async def zscore(self, key: str, member: str):
        return self._sync.zscore(key, member)

    async def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        return self._sync.zremrangebyrank(key, start, stop)

    async def expire(self, key: str, seconds: int) -> bool:
        return self._sync.expire(key, seconds)

    async def aclose(self) -> None:
        return None

    def pipeline(self) -> "AsyncFakePipeline":
        return AsyncFakePipeline(self._sync)


class AsyncFakePipeline:
    """Pipeline asíncrono que delega en `FakePipeline`."""

    def __init__(self, parent: FakeRedis) -> None:
        self._inner = FakePipeline(parent)

    def hset(self, key: str, mapping: dict | None = None) -> "AsyncFakePipeline":
        self._inner.hset(key, mapping=mapping)
        return self

    def hgetall(self, key: str) -> "AsyncFakePipeline":
        self._inner.hgetall(key)
        return self

    def delete(self, *keys: str) -> "AsyncFakePipeline":
        self._inner.delete(*keys)
        return self

    def rename(self, src: str, dst: str) -> "AsyncFakePipeline":
        self._inner.rename(src, dst)
        return self

    async def execute(self) -> list:
        return self._inner.execute()

    async def __aenter__(self) -> "AsyncFakePipeline":
        return self

    async def __aexit__(self, *_args) -> None:
        return None


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def auth_headers():
    """Devuelve un helper para generar cabeceras Bearer válidas."""
    from app.core.auth import issue_token

    def make(sub: str) -> dict[str, str]:
        token, _ = issue_token(sub)
        return {"Authorization": f"Bearer {token}"}

    return make


def _build_test_app(fake_redis: FakeRedis) -> FastAPI:
    """Construye una app mínima con Redis falso inyectado.

    Los clientes síncrono y asíncrono comparten almacenamiento, por lo que las
    inspecciones directas sobre `fake_redis` reflejan cambios hechos por routers.
    """
    from app.core.rate_limit import limiter
    from app.routers import auth, favorites, health, imports, parkings

    app = FastAPI()
    app.state.redis = AsyncFakeRedis(fake_redis)
    app.state.redis_sync = fake_redis
    app.state.limiter = limiter

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(imports.router)
    app.include_router(parkings.router)
    app.include_router(favorites.router)

    return app


@pytest.fixture
def api_client(fake_redis: FakeRedis) -> Iterator[TestClient]:
    """Cliente HTTP de test contra una aplicación sin datos iniciales."""
    app = _build_test_app(fake_redis)
    with TestClient(app) as client:
        yield client


_API_FEATURES_WITH_SOURCE: list[tuple[str, dict]] = [
    (
        "aparcamientos.geojson",
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-6.34204232, 39.47848638]},
            "properties": {
                "NOMBRE": "Escuela Politécnica",
                "NUCLEO": "CÁCERES",
                "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903",
            },
        },
    ),
    (
        "parkings.geojson",
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-6.3743148782, 39.4757325603]},
            "properties": {
                "name": "Obispo Galarza",
                "streetName": "OBISPO GALARZA",
                "streetType": "CALLE",
                "district": "CENTRO",
                "neighborhood": "CENTRO",
                "URL": "?mslink=2001",
            },
        },
    ),
    (
        "aparcamientos_en_linea.geojson",
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-6.3994515, 39.4670139],
                        [-6.3991710, 39.4663191],
                        [-6.3991416, 39.4663258],
                        [-6.3994238, 39.4670207],
                        [-6.3994515, 39.4670139],
                    ]
                ],
            },
            "properties": {
                "name": "Calle Dalia",
                "totalSpaces": 16,
                "streetName": "DALIA",
                "streetType": "CALLE",
                "district": "OESTE",
                "neighborhood": "EL JUNQUILLO",
                "URL": "?mslink=5500",
            },
        },
    ),
    (
        "aparcamientos_en_linea.geojson",
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-6.4022597, 39.4775947],
                    [-6.4022522, 39.4775983],
                    [-6.4022077, 39.4776199],
                ],
            },
            "properties": {
                "name": "Superficie Esquiladores",
                "URL": "?mslink=7700",
            },
        },
    ),
    (
        "zona_azul.geojson",
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-6.3828, 39.4711],
                        [-6.3825, 39.4714],
                        [-6.3824, 39.4714],
                        [-6.3828, 39.4711],
                    ]
                ],
            },
            "properties": {
                "name": "Rodriguez de Ledesma",
                "totalSpaces": 19,
                "streetName": "RODRIGUEZ DE LEDESMA",
                "district": "OESTE",
                "URL": "?mslink=9001",
            },
        },
    ),
    (
        "parking_motos_puntos.geojson",
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-6.38917, 39.46839]},
            "properties": {
                "name": "Calle Londres",
                "totalSpaces": 15,
                "streetName": "LONDRES",
                "URL": "?mslink=9100",
            },
        },
    ),
    (
        "parking_bicis.geojson",
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-6.3729966, 39.4707513]},
            "properties": {
                "name": "Calle Colon",
                "totalSpaces": 5,
                "streetName": "COLON",
                "district": "CENTRO",
                "URL": "?mslink=9200",
            },
        },
    ),
]


@pytest.fixture
def api_features_with_source() -> list[tuple[str, dict]]:
    """Devuelve copias independientes del dataset sintético."""
    import copy

    return copy.deepcopy(_API_FEATURES_WITH_SOURCE)


@pytest.fixture
def seeded_client(
    fake_redis: FakeRedis,
    api_features_with_source: list[tuple[str, dict]],
) -> Iterator[TestClient]:
    """Cliente HTTP de test con un catálogo sintético ya importado."""
    from app.infra.redis.importer import SOURCE_REGISTRY, run_import_sources

    buckets: dict[str, list[dict]] = {}

    for filename, feature in api_features_with_source:
        buckets.setdefault(filename, []).append(feature)

    sources = [
        (features, SOURCE_REGISTRY[filename])
        for filename, features in buckets.items()
    ]
    run_import_sources(sources, fake_redis)

    app = _build_test_app(fake_redis)
    with TestClient(app) as client:
        yield client