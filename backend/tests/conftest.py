"""Fixtures compartidos para los tests.

`fake_redis` es una implementación minimalista en memoria del subset de la
API de `redis-py` que usan el importador y los routers (`scan_iter`, `delete`,
`exists`, `geoadd`, `geosearch`, `hset`, `pipeline`, `hgetall`, `setex`, `get`,
`zadd`, `zrem`, `zrevrange`, `zscore`).

Mantenerla aquí (en lugar de añadir `fakeredis` como dependencia) tiene dos
ventajas:
- los tests no dependen de un paquete extra,
- el comportamiento queda explícito y auditable cuando algún test falla.

`api_client` arma un `FastAPI` minimal (sin lifespan) con el `FakeRedis`
inyectado en `app.state.redis`, y devuelve un `TestClient` listo para hacer
requests contra los endpoints reales.
"""

from __future__ import annotations

import math
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Radio de la Tierra en metros — usado por la implementación haversine de
# `geosearch`. No buscamos exactitud al milímetro: nos basta con que ordene
# correctamente y respete el radio en los tests.
_EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlamb / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class FakeRedis:
    """Subset de `redis.Redis(decode_responses=True)` en memoria.

    Modela cuatro tipos de claves:
    - `strings`: para `SET`/`SETEX`/`GET` (caché `cache:nearby:*`).
    - `hashes`: para `HSET`/`HGETALL` (`parking:{id}`).
    - `geo`: para `GEOADD`/`GEOSEARCH` (índice `geo:parkings`). Se guarda
      `{member: (lon, lat)}`; suficiente para verificar que el feature se
      indexó en la posición correcta.
    - `zsets`: sorted sets genéricos para `ZADD`/`ZREM`/`ZREVRANGE`/`ZSCORE`
      (favoritos por usuario `user:{id}:favorites`). `{member: score}`.
    """

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.geo: dict[str, dict[str, tuple[float, float]]] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    # ---------- API directa (no pipeline) ----------

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

    def geoadd(self, key: str, values) -> int:
        """Acepta `(lon, lat, member)` o lista plana `[lon, lat, member, ...]`."""
        bucket = self.geo.setdefault(key, {})
        added = 0
        if (
            isinstance(values, (list, tuple))
            and len(values) == 3
            and not isinstance(values[0], (list, tuple))
        ):
            lon, lat, member = values
            if member not in bucket:
                added += 1
            bucket[str(member)] = (float(lon), float(lat))
            return added
        # Lista plana
        for i in range(0, len(values), 3):
            lon, lat, member = values[i], values[i + 1], values[i + 2]
            if member not in bucket:
                added += 1
            bucket[str(member)] = (float(lon), float(lat))
        return added

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            for store in (self.hashes, self.strings, self.geo, self.zsets):
                if k in store:
                    del store[k]
                    n += 1
        return n

    def exists(self, *keys: str) -> int:
        # Como el real: cuenta cuántas de las claves pasadas existen (en
        # cualquier tipo). Suficiente para los chequeos de "parking:{id}".
        n = 0
        for k in keys:
            for store in (self.hashes, self.strings, self.geo, self.zsets):
                if k in store:
                    n += 1
                    break
        return n

    def scan_iter(self, match: str | None = None) -> Iterator[str]:
        all_keys = (
            list(self.hashes.keys())
            + list(self.strings.keys())
            + list(self.geo.keys())
            + list(self.zsets.keys())
        )
        if match is None:
            yield from all_keys
            return
        # Solo soportamos el patrón `prefijo*` (lo único que usa el importador).
        if match.endswith("*"):
            prefix = match[:-1]
            for k in all_keys:
                if k.startswith(prefix):
                    yield k
            return
        for k in all_keys:
            if k == match:
                yield k

    def setex(self, key: str, ttl: int, value: str) -> bool:
        # No simulamos expiración (no hace falta en estos tests).
        self.strings[key] = str(value)
        return True

    def get(self, key: str) -> str | None:
        return self.strings.get(key)

    def zscore(self, key: str, member: str) -> float | None:
        # Prioriza sorted sets genéricos (ZSCORE real para favoritos).
        zset = self.zsets.get(key)
        if zset is not None:
            return zset.get(member)
        # Fallback histórico: devolver algo no-None si el miembro está en el
        # índice geoespacial (los tests del importador comprueban presencia).
        if member in self.geo.get(key, {}):
            return 1.0
        return None

    # ---------- Sorted sets genéricos (favoritos) ----------

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
        n = 0
        for m in members:
            if m in bucket:
                del bucket[m]
                n += 1
        # Limpiamos la clave si queda vacía, igual que hace Redis con sorted sets.
        if not bucket:
            del self.zsets[key]
        return n

    def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        """Subset de `ZREVRANGE`: miembros ordenados por score descendente.

        Soporta `end == -1` (hasta el final). En empates de score Redis ordena
        lexicográfico DESC; lo emulamos con dos `sorted` estables consecutivos
        (primero por miembro DESC, luego por score DESC).
        """
        bucket = self.zsets.get(key, {})
        if not bucket:
            return []
        # Estable: primero criterio secundario (miembro DESC), luego primario (score DESC).
        items = sorted(bucket.items(), key=lambda kv: kv[0], reverse=True)
        items = sorted(items, key=lambda kv: kv[1], reverse=True)
        members = [m for m, _ in items]
        if end == -1:
            return members[start:]
        return members[start : end + 1]

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def geosearch(
        self,
        key: str,
        *,
        longitude: float,
        latitude: float,
        radius: float,
        unit: str = "m",
        withdist: bool = False,
        sort: str | None = None,
    ):
        """Subset de `GEOSEARCH FROMLONLAT BYRADIUS`.

        Solo soporta `unit='m'`, suficiente para los tests del backend (los
        endpoints siempre piden metros). `withdist=True` devuelve `[member, dist]`
        en cada fila; `sort='ASC'` ordena por distancia ascendente.
        """
        if unit != "m":
            raise NotImplementedError("FakeRedis.geosearch solo soporta unit='m'")

        bucket = self.geo.get(key, {})
        rows: list[tuple[str, float]] = []
        for member, (mlon, mlat) in bucket.items():
            dist = _haversine_m(latitude, longitude, mlat, mlon)
            if dist <= radius:
                rows.append((member, dist))

        if sort == "ASC":
            rows.sort(key=lambda r: r[1])
        elif sort == "DESC":
            rows.sort(key=lambda r: r[1], reverse=True)

        if withdist:
            return [[member, dist] for member, dist in rows]
        return [member for member, _ in rows]

    # ---------- Pipeline ----------

    def pipeline(self) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    """Pipeline que acumula comandos y los aplica al ejecutar.

    No reordena ni optimiza: ejecuta en el orden recibido contra el `FakeRedis`
    padre. Suficiente para verificar que el importador llama a las primitivas
    correctas y en el orden esperado.
    """

    def __init__(self, parent: FakeRedis) -> None:
        self.parent = parent
        self._cmds: list[tuple] = []

    def delete(self, *keys: str) -> "FakePipeline":
        self._cmds.append(("delete", keys))
        return self

    def geoadd(self, key: str, values) -> "FakePipeline":
        self._cmds.append(("geoadd", key, values))
        return self

    def hset(self, key: str, mapping: dict | None = None) -> "FakePipeline":
        self._cmds.append(("hset", key, mapping))
        return self

    def hgetall(self, key: str) -> "FakePipeline":
        self._cmds.append(("hgetall", key))
        return self

    def execute(self) -> list:
        results = []
        for cmd in self._cmds:
            if cmd[0] == "delete":
                results.append(self.parent.delete(*cmd[1]))
            elif cmd[0] == "geoadd":
                results.append(self.parent.geoadd(cmd[1], cmd[2]))
            elif cmd[0] == "hset":
                results.append(self.parent.hset(cmd[1], mapping=cmd[2]))
            elif cmd[0] == "hgetall":
                results.append(self.parent.hgetall(cmd[1]))
        self._cmds.clear()
        return results


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


# ============================================================
# Fixtures de FastAPI: TestClient con FakeRedis inyectado
# ============================================================

def _build_test_app(fake_redis: FakeRedis) -> FastAPI:
    """Monta una app FastAPI mínima sin lifespan, lista para `TestClient`.

    Importamos los routers DENTRO de la función para que cada test arranque
    desde un estado limpio y no haya efectos colaterales del orden de imports.
    """
    from app.routers import favorites, health, imports, parkings

    app = FastAPI()
    app.state.redis = fake_redis
    app.include_router(health.router)
    app.include_router(imports.router)
    app.include_router(parkings.router)
    app.include_router(favorites.router)
    return app


@pytest.fixture
def api_client(fake_redis: FakeRedis) -> Iterator[TestClient]:
    """`TestClient` contra una app vacía (sin datos en Redis).

    Útil para probar respuestas con catálogo vacío o errores antes de seed.
    """
    app = _build_test_app(fake_redis)
    with TestClient(app) as client:
        yield client


# ============================================================
# Dataset sintético para los tests de API
# ============================================================
#
# Mezcla los 3 tipos de geometría + variedad de category/regulation/vehicleType
# y de campos opcionales (totalSpaces, accent-insensitive en `name`/`district`).
# Diseñado para ejercitar los filtros de los endpoints sin necesidad de leer
# ficheros reales.

_API_FEATURES: list[dict] = [
    {  # POINT, parking público gratuito, sin totalSpaces.
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-6.34204232, 39.47848638]},
        "properties": {
            "NOMBRE": "Escuela Politécnica",
            "NUCLEO": "CÁCERES",
            "URL": "http://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903",
        },
    },
    {  # POINT, paid_parking en el centro.
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-6.3743148782, 39.4757325603]},
        "properties": {
            "name": "Obispo Galarza",
            "category": "paid_parking",
            "vehicleType": "car",
            "regulation": "paid",
            "streetName": "OBISPO GALARZA",
            "streetType": "CALLE",
            "district": "CENTRO",
            "neighborhood": "CENTRO",
            "URL": "?mslink=2001",
        },
    },
    {  # POLYGON, street_line con totalSpaces.
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
            "category": "street_line",
            "vehicleType": "car",
            "regulation": "free",
            "totalSpaces": 16,
            "streetName": "DALIA",
            "streetType": "CALLE",
            "district": "OESTE",
            "neighborhood": "EL JUNQUILLO",
            "URL": "?mslink=5500",
        },
    },
    {  # LINE_STRING.
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
            "category": "street_line",
            "regulation": "free",
            "URL": "?mslink=7700",
        },
    },
    {  # POLYGON, blue_zone con muchas plazas.
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
            "category": "blue_zone",
            "vehicleType": "car",
            "regulation": "blue_zone",
            "totalSpaces": 19,
            "streetName": "RODRIGUEZ DE LEDESMA",
            "district": "OESTE",
            "URL": "?mslink=9001",
        },
    },
    {  # POINT, parking de motos.
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-6.38917, 39.46839]},
        "properties": {
            "name": "Calle Londres",
            "category": "motorbike",
            "vehicleType": "motorbike",
            "regulation": "reserved",
            "totalSpaces": 15,
            "streetName": "LONDRES",
            "URL": "?mslink=9100",
        },
    },
    {  # POINT, parking de bicis.
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-6.3729966, 39.4707513]},
        "properties": {
            "name": "Calle Colon",
            "category": "bicycle",
            "vehicleType": "bike",
            "regulation": "reserved",
            "totalSpaces": 5,
            "streetName": "COLON",
            "district": "CENTRO",
            "URL": "?mslink=9200",
        },
    },
]


@pytest.fixture
def api_features() -> list[dict]:
    """Devuelve copias frescas (los tests no comparten mutación entre sí)."""
    import copy
    return copy.deepcopy(_API_FEATURES)


@pytest.fixture
def seeded_client(
    fake_redis: FakeRedis, api_features: list[dict]
) -> Iterator[TestClient]:
    """`TestClient` con el dataset sintético ya importado en Redis."""
    from app.importer import run_import

    run_import(api_features, fake_redis)
    app = _build_test_app(fake_redis)
    with TestClient(app) as client:
        yield client
