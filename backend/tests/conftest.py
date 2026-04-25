"""Fixtures compartidos para los tests.

`fake_redis` es una implementación minimalista en memoria del subset de la
API de `redis-py` que usa el importador. No pretende ser un sustituto general
de Redis: solo cubre los comandos que se ejercitan en el flujo de import
(`scan_iter`, `delete`, `geoadd`, `hset`, `pipeline`, `hgetall`, `setex`,
`get`, `zscore`).

Mantenerla aquí (en lugar de añadir `fakeredis` como dependencia) tiene dos
ventajas:
- los tests no dependen de un paquete extra,
- el comportamiento queda explícito y auditable cuando algún test falla.
"""

from __future__ import annotations

from typing import Iterator

import pytest


class FakeRedis:
    """Subset de `redis.Redis(decode_responses=True)` en memoria.

    Modela tres tipos de claves:
    - `strings`: para `SET`/`SETEX`/`GET` (caché `cache:nearby:*`).
    - `hashes`: para `HSET`/`HGETALL` (`parking:{id}`).
    - `geo`: para `GEOADD`/`ZSCORE` (índice `geo:parkings`). Se guarda
      `{member: (lon, lat)}`; suficiente para verificar que el feature se
      indexó en la posición correcta.
    """

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.geo: dict[str, dict[str, tuple[float, float]]] = {}

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
            for store in (self.hashes, self.strings, self.geo):
                if k in store:
                    del store[k]
                    n += 1
        return n

    def scan_iter(self, match: str | None = None) -> Iterator[str]:
        all_keys = (
            list(self.hashes.keys())
            + list(self.strings.keys())
            + list(self.geo.keys())
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
        bucket = self.geo.get(key, {})
        if member not in bucket:
            return None
        # No emulamos el geohash real; devolver algo no-None es suficiente
        # para los asserts del test.
        return 1.0

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

    def execute(self) -> list:
        results = []
        for cmd in self._cmds:
            if cmd[0] == "delete":
                results.append(self.parent.delete(*cmd[1]))
            elif cmd[0] == "geoadd":
                results.append(self.parent.geoadd(cmd[1], cmd[2]))
            elif cmd[0] == "hset":
                results.append(self.parent.hset(cmd[1], mapping=cmd[2]))
        self._cmds.clear()
        return results


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
