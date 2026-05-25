"""Tests del endpoint de salud.

Verifican el estado correcto con Redis disponible y los estados degradados ante
fallo de conexión o índice de búsqueda vacío.
"""

from __future__ import annotations

import redis


def test_healthz_ok_with_fake_redis(api_client):
    response = api_client.get("/healthz")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["redis"] == {"status": "ok"}
    assert payload["search_index"]["status"] == "ok"
    assert payload["search_index"]["num_docs"] is None


def test_healthz_503_when_redis_down(api_client):
    real_redis = api_client.app.state.redis

    class DeadRedis:
        async def ping(self):
            raise redis.ConnectionError("nope")

        async def execute_command(self, *_args, **_kwargs):
            raise redis.ConnectionError("nope")

    api_client.app.state.redis = DeadRedis()

    try:
        response = api_client.get("/healthz")
    finally:
        api_client.app.state.redis = real_redis

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["redis"]["status"] == "down"
    assert payload["search_index"] == {"status": "unknown"}


def test_root_still_returns_simple_payload(api_client):
    response = api_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "Backend configurado y listo"}


def test_healthz_503_when_search_index_is_empty(api_client):
    real_redis = api_client.app.state.redis

    class EmptyIndexRedis:
        async def ping(self):
            return True

        async def execute_command(self, *args, **_kwargs):
            assert args[0] == "FT.INFO"
            return ["index_name", args[1], "num_docs", 0]

    api_client.app.state.redis = EmptyIndexRedis()

    try:
        response = api_client.get("/healthz")
    finally:
        api_client.app.state.redis = real_redis

    assert response.status_code == 503

    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["redis"]["status"] == "ok"
    assert payload["search_index"]["status"] == "empty"
    assert payload["search_index"]["num_docs"] == 0