"""Tests del healthcheck `GET /healthz`.

`FakeRedis` no expone `execute_command`, así que el handler entra por la rama
de degradación grácil que devuelve `num_docs: None` con `status: ok`. Con un
cliente "muerto" (que lanza `ConnectionError` en `ping`) la respuesta es 503
con desglose por componente.
"""

from __future__ import annotations

import redis


def test_healthz_ok_with_fake_redis(api_client):
    response = api_client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["redis"] == {"status": "ok"}
    # FakeRedis no implementa execute_command -> el handler lo trata como
    # "ok" con num_docs desconocido.
    assert payload["search_index"]["status"] == "ok"
    assert payload["search_index"]["num_docs"] is None


def test_healthz_503_when_redis_down(api_client):
    """Si el ping a Redis falla, /healthz devuelve 503 con desglose."""
    real_redis = api_client.app.state.redis

    class DeadRedis:
        def ping(self):
            raise redis.ConnectionError("nope")

        def execute_command(self, *_args, **_kwargs):
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
    # Si Redis está caído, no hace falta intentar FT.INFO.
    assert payload["search_index"] == {"status": "unknown"}


def test_root_still_returns_simple_payload(api_client):
    response = api_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "Backend configurado y listo"}
