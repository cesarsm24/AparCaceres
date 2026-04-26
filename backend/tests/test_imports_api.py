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
