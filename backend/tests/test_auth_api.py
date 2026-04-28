"""Tests del módulo de autenticación (`/auth/session` + `require_user`).

Cubren los caminos felices y los modos de fallo más probables: secreto sin
configurar, token caducado, sub con caracteres prohibidos, cabecera mal
formada.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core import auth as auth_module

# ============================================================
# POST /auth/session
# ============================================================

def test_create_session_returns_jwt_with_sub(api_client):
    response = api_client.post("/auth/session", json={"sub": "alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == "alice"
    assert body["tokenType"] == "Bearer"
    assert body["expiresAt"].endswith("+00:00")

    # El token debe descodificarse con el mismo secreto y devolver el sub.
    decoded = jwt.decode(body["token"], "test-secret-do-not-leak", algorithms=["HS256"])
    assert decoded["sub"] == "alice"
    assert "exp" in decoded
    assert "iat" in decoded


def test_create_session_400_when_sub_has_forbidden_chars(api_client):
    response = api_client.post("/auth/session", json={"sub": "ali:ce"})
    assert response.status_code == 400


def test_create_session_400_when_sub_blank(api_client):
    response = api_client.post("/auth/session", json={"sub": "   "})
    assert response.status_code == 400


def test_create_session_503_when_secret_missing(api_client, monkeypatch):
    """Sin FAVORITES_SECRET y fuera de dev, emitir falla con 503 fail-closed."""
    monkeypatch.delenv("FAVORITES_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")

    response = api_client.post("/auth/session", json={"sub": "alice"})
    assert response.status_code == 503
    assert "FAVORITES_SECRET" in response.json()["detail"]


# ============================================================
# require_user (vía favoritos)
# ============================================================

def test_expired_token_rejected_with_401(seeded_client):
    """JWT con `exp` en el pasado → 401."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": "alice", "iat": int(past.timestamp()), "exp": int(past.timestamp())},
        "test-secret-do-not-leak",
        algorithm="HS256",
    )
    response = seeded_client.get(
        "/users/me/favorites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "expirado" in response.json()["detail"].lower()


def test_token_signed_with_other_key_rejected(seeded_client):
    """JWT firmado con otra clave → 401 (firma inválida)."""
    token = jwt.encode({"sub": "alice"}, "wrong-key", algorithm="HS256")
    response = seeded_client.get(
        "/users/me/favorites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_dev_fallback_secret_logs_warning(monkeypatch, caplog):
    monkeypatch.delenv("FAVORITES_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "development")

    with caplog.at_level("WARNING", logger=auth_module.logger.name):
        secret = auth_module._resolve_secret()

    assert secret == "dev-only-secret-do-not-use-in-prod"
    assert any("FAVORITES_SECRET" in rec.message for rec in caplog.records)


def test_resolve_secret_none_in_production_without_env(monkeypatch):
    monkeypatch.delenv("FAVORITES_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert auth_module._resolve_secret() is None
