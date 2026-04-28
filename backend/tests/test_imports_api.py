"""Tests del endpoint protegido de importación.

Verifican la validación del token de importación, la integración con rate
limiting y la invalidación de caché tras ejecutar un reimport.
"""

from __future__ import annotations

from app.routers import imports as imports_router


def _stub_import(monkeypatch):
    """Sustituye la importación real por una respuesta estable."""
    monkeypatch.setattr(
        imports_router,
        "run_import_dir",
        lambda data_dir, rdb: {"status": "ok", "imported": 0},
    )


def test_import_parkings_is_open_when_token_is_not_configured(api_client, monkeypatch):
    _stub_import(monkeypatch)
    monkeypatch.setattr(imports_router, "IMPORT_TOKEN", "")

    response = api_client.post("/import-parkings")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_import_parkings_requires_token_when_configured(api_client, monkeypatch):
    _stub_import(monkeypatch)
    monkeypatch.setattr(imports_router, "IMPORT_TOKEN", "secret")

    missing = api_client.post("/import-parkings")
    wrong = api_client.post("/import-parkings", headers={"X-Import-Token": "nope"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_import_parkings_accepts_valid_token(api_client, monkeypatch):
    _stub_import(monkeypatch)
    monkeypatch.setattr(imports_router, "IMPORT_TOKEN", "secret")

    response = api_client.post("/import-parkings", headers={"X-Import-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_import_parkings_works_with_rate_limiter_enabled(api_client, monkeypatch):
    _stub_import(monkeypatch)
    monkeypatch.setattr(imports_router, "IMPORT_TOKEN", "")
    monkeypatch.setattr(imports_router.limiter, "enabled", True)

    imports_router.limiter.reset()

    response = api_client.post("/import-parkings")

    assert response.status_code == 200
    assert any(header.lower().startswith("x-ratelimit") for header in response.headers)


def test_import_increments_cache_version_for_nearby_namespacing(
    seeded_client, fake_redis, monkeypatch
):
    from app.core.config import CACHE_VERSION_KEY
    from app.routers import imports as imports_router

    monkeypatch.setattr(
        imports_router,
        "run_import_dir",
        lambda data_dir, rdb: {
            "status": "ok",
            "imported": 0,
            "cache_version": int(rdb.incr(CACHE_VERSION_KEY)),
        },
    )

    initial_version = int(fake_redis.get(CACHE_VERSION_KEY) or "0")

    response = seeded_client.post(
        "/import-parkings",
        headers={"X-Import-Token": imports_router.IMPORT_TOKEN},
    )

    assert response.status_code == 200

    new_version = int(fake_redis.get(CACHE_VERSION_KEY))

    assert new_version == initial_version + 1
    assert response.json()["cache_version"] == new_version

    nearby = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.47, "lng": -6.37},
    )

    assert nearby.status_code == 200

    cached_keys = [key for key in fake_redis.strings if key.startswith("cache:nearby:")]

    assert any(f"v{new_version}:" in key for key in cached_keys)