"""Tests de autenticación por token de sesión.

Verifican la emisión de JWT, la validación de sujetos permitidos y los fallos
esperados ante configuración ausente, expiración o firma inválida.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core import auth as auth_module


def test_create_session_returns_jwt_with_sub(api_client):
    response = api_client.post("/auth/session", json={"sub": "alice"})

    assert response.status_code == 200

    body = response.json()
    assert body["sub"] == "alice"
    assert body["tokenType"] == "Bearer"
    assert body["expiresAt"].endswith("+00:00")

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
    monkeypatch.delenv("FAVORITES_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")

    response = api_client.post("/auth/session", json={"sub": "alice"})

    assert response.status_code == 503
    assert "configurada" in response.json()["detail"]


def test_expired_token_rejected_with_401(seeded_client):
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
    token = jwt.encode({"sub": "alice"}, "wrong-key", algorithm="HS256")

    response = seeded_client.get(
        "/users/me/favorites",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_resolve_secret_none_when_missing(monkeypatch):
    monkeypatch.delenv("FAVORITES_SECRET", raising=False)

    assert auth_module._resolve_secret() is None