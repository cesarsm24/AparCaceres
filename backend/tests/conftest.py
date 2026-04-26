"""Fixtures compartidos para los tests.

`fake_redis` es una implementación minimalista en memoria del subset de la
API de `redis-py` que usan el importador y los routers (`scan_iter`, `delete`,
`exists`, `hset`, `pipeline`, `hgetall`, `setex`, `get`, `zadd`, `zrem`,
`zrevrange`, `zscore`, `ping`).

Mantenerla aquí (en lugar de añadir `fakeredis` como dependencia) tiene dos
ventajas:
- los tests no dependen de un paquete extra,
- el comportamiento queda explícito y auditable cuando algún test falla.

`api_client` arma un `FastAPI` minimal (sin lifespan) con el `FakeRedis`
inyectado en `app.state.redis`, y devuelve un `TestClient` listo para hacer
requests contra los endpoints reales.

Rate limiting: forzamos `RATE_LIMIT_ENABLED=false` antes de cualquier import
de la app para que el limiter de slowapi sea inerte en la suite. Los tests
dedicados al rate limit lo reactivan localmente.
"""

from __future__ import annotations

import os

# Debe ejecutarse ANTES de importar la app (incluye `app.rate_limit`).
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("METRICS_ENABLED", "false")
# Clave de firma fija para los tokens de favoritos. Cualquier valor sirve;
# solo importa que sea estable durante la suite.
os.environ.setdefault("FAVORITES_SECRET", "test-secret-do-not-leak")

from typing import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class FakeRedis:
    """Subset de `redis.Redis(decode_responses=True)` en memoria.

    Modela cinco tipos de claves:
    - `strings`: para `SET`/`SETEX`/`GET` (caché `cache:nearby:*`).
    - `hashes`: para `HSET`/`HGETALL` (`parking:{id}`).
    - `zsets`: sorted sets para `ZADD`/`ZREM`/`ZREVRANGE`/`ZSCORE` (favoritos
      por usuario `user:{id}:favorites`). `{member: score}`.
    """

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    # ---------- API directa (no pipeline) ----------

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
        n = 0
        for k in keys:
            for store in (self.hashes, self.strings, self.zsets):
                if k in store:
                    del store[k]
                    n += 1
        return n

    def exists(self, *keys: str) -> int:
        # Como el real: cuenta cuántas de las claves pasadas existen (en
        # cualquier tipo). Suficiente para los chequeos de "parking:{id}".
        n = 0
        for k in keys:
            for store in (self.hashes, self.strings, self.zsets):
                if k in store:
                    n += 1
                    break
        return n

    def scan_iter(self, match: str | None = None) -> Iterator[str]:
        all_keys = (
            list(self.hashes.keys())
            + list(self.strings.keys())
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

    def incr(self, key: str, amount: int = 1) -> int:
        """Subset de `INCR` / `INCRBY`: inicializa a 0 si no existe."""
        current = int(self.strings.get(key, "0") or "0")
        new_value = current + int(amount)
        self.strings[key] = str(new_value)
        return new_value

    def zscore(self, key: str, member: str) -> float | None:
        zset = self.zsets.get(key)
        if zset is not None:
            return zset.get(member)
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

    def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        """Subset de `ZREMRANGEBYRANK`: elimina por rango ascendente de score.

        Soporta índices negativos como Redis (`-1` = último). Empates de
        score: se ordena por miembro ASC para que el resultado sea determinista
        en los tests. Si tras el borrado el sorted set queda vacío, eliminamos
        la clave (igual que Redis).
        """
        bucket = self.zsets.get(key)
        if not bucket:
            return 0
        ordered = sorted(bucket.items(), key=lambda kv: (kv[1], kv[0]))
        n = len(ordered)
        # Normaliza índices negativos al estilo Redis.
        s = start if start >= 0 else max(n + start, 0)
        e = stop if stop >= 0 else n + stop
        if s > e or s >= n:
            return 0
        e = min(e, n - 1)
        victims = [member for member, _ in ordered[s : e + 1]]
        for m in victims:
            bucket.pop(m, None)
        if not bucket:
            del self.zsets[key]
        return len(victims)

    def expire(self, key: str, seconds: int) -> bool:
        """Subset de `EXPIRE`: aceptamos la llamada como no-op (no simulamos TTL)."""
        for store in (self.hashes, self.strings, self.zsets):
            if key in store:
                return True
        return False

    def rename(self, src: str, dst: str) -> bool:
        """Subset de RENAME: mueve la clave entre stores. Lanza KeyError si no existe."""
        for store in (self.hashes, self.strings, self.zsets):
            if src in store:
                store[dst] = store.pop(src)
                return True
        raise KeyError(f"no such key: {src}")

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
            elif cmd[0] == "hset":
                results.append(self.parent.hset(cmd[1], mapping=cmd[2]))
            elif cmd[0] == "hgetall":
                results.append(self.parent.hgetall(cmd[1]))
            elif cmd[0] == "rename":
                results.append(self.parent.rename(cmd[1], cmd[2]))
        self._cmds.clear()
        return results


# ============================================================
# Adaptador async sobre FakeRedis
# ============================================================
#
# Los routers async esperan un cliente que se parezca a `redis.asyncio.Redis`:
# coroutines en lugar de métodos síncronos y un `pipeline()` cuyo `execute()`
# también sea coroutine.
# `AsyncFakeRedis` envuelve un `FakeRedis` concreto y delega todo en él, así
# los tests pueden seguir inspeccionando el estado a través del `FakeRedis`
# síncrono compartido (`fake_redis.hashes`, etc.).

class AsyncFakeRedis:
    """Adaptador async mínimo: solo expone los comandos que usan los routers."""

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
    """Pipeline async: delega en `FakePipeline` y expone `execute()` async."""

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
    """Devuelve un helper `make(sub)` que produce las cabeceras Bearer."""
    from app.auth import issue_token

    def make(sub: str) -> dict[str, str]:
        token, _ = issue_token(sub)
        return {"Authorization": f"Bearer {token}"}

    return make


# ============================================================
# Fixtures de FastAPI: TestClient con FakeRedis inyectado
# ============================================================

def _build_test_app(fake_redis: FakeRedis) -> FastAPI:
    """Monta una app FastAPI mínima sin lifespan, lista para `TestClient`.

    Importamos los routers DENTRO de la función para que cada test arranque
    desde un estado limpio y no haya efectos colaterales del orden de imports.

    `app.state.redis` es el cliente "async" (AsyncFakeRedis) y
    `app.state.redis_sync` es el síncrono (FakeRedis). Comparten almacenamiento,
    así que las inspecciones directas (`fake_redis.hashes`) ven los cambios
    hechos por cualquiera de los dos.
    """
    from app.rate_limit import limiter
    from app.routers import auth, favorites, health, imports, parkings

    app = FastAPI()
    app.state.redis = AsyncFakeRedis(fake_redis)
    app.state.redis_sync = fake_redis
    # slowapi exige `app.state.limiter`; con `enabled=False` (forzado en este
    # fichero) los decoradores `@limiter.limit(...)` no aplican cupo alguno.
    app.state.limiter = limiter
    app.include_router(health.router)
    app.include_router(auth.router)
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
# Cada feature está emparejado con su `SourceProfile` real para que los ids
# resultantes sean namespaced (`{sourceDataset}:{mslink}`).

# (filename del dataset en SOURCE_REGISTRY, feature)
_API_FEATURES_WITH_SOURCE: list[tuple[str, dict]] = [
    (
        "aparcamientos.geojson",
        {  # POINT, parking público gratuito, sin totalSpaces.
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
        {  # POINT, paid_parking en el centro.
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
                "URL": "?mslink=7700",
            },
        },
    ),
    (
        "zona_azul.geojson",
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
                "totalSpaces": 19,
                "streetName": "RODRIGUEZ DE LEDESMA",
                "district": "OESTE",
                "URL": "?mslink=9001",
            },
        },
    ),
    (
        "parking_motos_puntos.geojson",
        {  # POINT, parking de motos.
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
        {  # POINT, parking de bicis.
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
    """Devuelve copias frescas (los tests no comparten mutación entre sí)."""
    import copy
    return copy.deepcopy(_API_FEATURES_WITH_SOURCE)


@pytest.fixture
def seeded_client(
    fake_redis: FakeRedis,
    api_features_with_source: list[tuple[str, dict]],
) -> Iterator[TestClient]:
    """`TestClient` con el dataset sintético ya importado en Redis.

    Cada feature se empareja con su `SourceProfile` para que los ids sean
    namespaced (`{sourceDataset}:{mslink}`), igual que en producción.
    """
    from app.importer import SOURCE_REGISTRY, run_import_sources

    # Bucket por filename para conservar el agrupamiento por dataset que usa
    # `run_import_sources`.
    buckets: dict[str, list[dict]] = {}
    for filename, feat in api_features_with_source:
        buckets.setdefault(filename, []).append(feat)

    sources = [
        (features, SOURCE_REGISTRY[filename])
        for filename, features in buckets.items()
    ]
    run_import_sources(sources, fake_redis)

    app = _build_test_app(fake_redis)
    with TestClient(app) as client:
        yield client
