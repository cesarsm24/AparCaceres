"""Tests del endpoint protegido de importación."""

from __future__ import annotations

from app.routers import imports as imports_router


def _stub_import(monkeypatch):
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
    """Regresión: con `@limiter.limit(...)` activo, slowapi inyecta cabeceras
    `X-RateLimit-*` y para ello necesita un parámetro `response: Response` en
    el handler. Sin él lanza `parameter response must be an instance of
    starlette.responses.Response` y devuelve 500.

    En el resto de la suite el limiter está deshabilitado (los decoradores
    son no-op), así que la regresión solo se ve aquí, activándolo a mano.
    """
    _stub_import(monkeypatch)
    monkeypatch.setattr(imports_router, "IMPORT_TOKEN", "")
    monkeypatch.setattr(imports_router.limiter, "enabled", True)
    # El cupo 1/min es global para slowapi; reseteamos el storage para que
    # los hits acumulados por tests previos (o por reordering) no nos cuelen
    # un 429 inesperado en este caso.
    imports_router.limiter.reset()

    response = api_client.post("/import-parkings")

    assert response.status_code == 200
    # slowapi añade estas cabeceras cuando `headers_enabled=True`.
    assert any(h.lower().startswith("x-ratelimit") for h in response.headers)


def test_import_increments_cache_version_for_nearby_namespacing(
    seeded_client, fake_redis, monkeypatch
):
    """Tras un re-import, `cache:version` debe subir y la clave de caché de
    `/parkings/nearby` la incluye como prefijo `v{n}`. Las entradas previas
    quedan inalcanzables al cambiar el namespace y caducan por TTL (O(1)).
    """
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

    response = seeded_client.post("/import-parkings")
    assert response.status_code == 200

    new_version = int(fake_redis.get(CACHE_VERSION_KEY))
    assert new_version == initial_version + 1
    assert response.json()["cache_version"] == new_version

    nearby = seeded_client.get(
        "/parkings/nearby", params={"lat": 39.47, "lng": -6.37}
    )
    assert nearby.status_code == 200
    # Una nueva entrada de caché aparece con el prefijo `v{n}` actual.
    cached_keys = [k for k in fake_redis.strings if k.startswith("cache:nearby:")]
    assert any(f"v{new_version}:" in k for k in cached_keys)
