"""Tests HTTP de favoritos de usuario.

Cubren autenticación, alta, baja, listado, aislamiento por usuario y límites de
almacenamiento. El catálogo usado es el dataset sintético importado por la
fixture `seeded_client`.
"""

from __future__ import annotations

import pytest

_REQUIRED_PLACE_FIELDS = {
    "id", "name", "category", "vehicleType", "regulation",
    "geometryType", "latitude", "longitude", "coordinates",
    "totalSpaces", "streetName", "streetType", "district",
    "neighborhood", "sourceDataset", "imageUrl", "urlFicha",
    "urlVia", "management",
}


def _assert_place_shape(place: dict) -> None:
    """Verifica que la respuesta mantiene el contrato público de aparcamientos."""
    assert _REQUIRED_PLACE_FIELDS.issubset(place.keys()), (
        f"Faltan campos: {_REQUIRED_PLACE_FIELDS - place.keys()}"
    )


@pytest.fixture
def freeze_time(monkeypatch):
    """Permite avanzar manualmente el reloj usado para ordenar favoritos."""
    state = {"now_ms": 1_700_000_000_000}

    def fake_now() -> int:
        return state["now_ms"]

    monkeypatch.setattr("app.routers.favorites._now_ms", fake_now)

    def tick(delta_ms: int) -> int:
        state["now_ms"] += delta_ms
        return state["now_ms"]

    return tick


def test_put_favorite_creates_entry_and_returns_payload(seeded_client, auth_headers):
    response = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=auth_headers("alice"),
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"] == "aparcamientos_en_linea:5500"
    assert body["created"] is True
    assert body["addedAt"].endswith("+00:00")


def test_put_favorite_is_idempotent_keeps_added_at(
    seeded_client, freeze_time, auth_headers
):
    headers = auth_headers("alice")

    first = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=headers,
    )
    assert first.json()["created"] is True

    original_added_at = first.json()["addedAt"]

    freeze_time(60_000)

    second = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["addedAt"] == original_added_at


def test_put_favorite_404_when_parking_does_not_exist(seeded_client, auth_headers):
    response = seeded_client.put(
        "/users/me/favorites/no-existe",
        headers=auth_headers("alice"),
    )

    assert response.status_code == 404
    assert "no-existe" in response.json()["detail"]


def test_put_favorite_401_when_no_bearer_token(seeded_client):
    response = seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500")

    assert response.status_code == 401
    assert "token" in response.json()["detail"].lower()


def test_put_favorite_401_when_bearer_malformed(seeded_client):
    response = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"Authorization": "NotBearer xyz"},
    )

    assert response.status_code == 401


def test_put_favorite_401_when_token_invalid(seeded_client):
    response = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401


def test_delete_favorite_removes_existing_entry(seeded_client, auth_headers):
    headers = auth_headers("alice")

    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)

    response = seeded_client.delete(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "aparcamientos_en_linea:5500", "removed": True}

    listing = seeded_client.get("/users/me/favorites", headers=headers).json()

    assert listing == []


def test_delete_favorite_returns_removed_false_when_not_in_list(
    seeded_client, auth_headers
):
    response = seeded_client.delete(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=auth_headers("alice"),
    )

    assert response.status_code == 200
    assert response.json() == {"id": "aparcamientos_en_linea:5500", "removed": False}


def test_delete_favorite_404_when_parking_does_not_exist(seeded_client, auth_headers):
    response = seeded_client.delete(
        "/users/me/favorites/no-existe",
        headers=auth_headers("alice"),
    )

    assert response.status_code == 404


def test_delete_favorite_401_when_no_bearer_token(seeded_client):
    response = seeded_client.delete("/users/me/favorites/aparcamientos_en_linea:5500")

    assert response.status_code == 401


def test_get_favorites_empty_when_user_has_none(seeded_client, auth_headers):
    response = seeded_client.get(
        "/users/me/favorites",
        headers=auth_headers("alice"),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_favorites_returns_full_parking_place_shape(seeded_client, auth_headers):
    headers = auth_headers("alice")

    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)

    response = seeded_client.get("/users/me/favorites", headers=headers)

    assert response.status_code == 200

    body = response.json()
    assert len(body) == 1

    _assert_place_shape(body[0])

    assert body[0]["id"] == "aparcamientos_en_linea:5500"
    assert body[0]["name"] == "Calle Dalia"
    assert body[0]["totalSpaces"] == 16
    assert body[0]["geometryType"] == "polygon"
    assert body[0]["coordinates"][0][0] == [-6.3994515, 39.4670139]


def test_get_favorites_orders_by_most_recent_first(
    seeded_client, freeze_time, auth_headers
):
    headers = auth_headers("alice")

    seeded_client.put("/users/me/favorites/aparcamientos:1903", headers=headers)
    freeze_time(1_000)
    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)
    freeze_time(1_000)
    seeded_client.put("/users/me/favorites/parking_motos_puntos:9100", headers=headers)

    response = seeded_client.get("/users/me/favorites", headers=headers)
    ids = [place["id"] for place in response.json()]

    assert ids == [
        "parking_motos_puntos:9100",
        "aparcamientos_en_linea:5500",
        "aparcamientos:1903",
    ]


def test_get_favorites_isolated_per_user(seeded_client, auth_headers):
    seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=auth_headers("alice"),
    )
    seeded_client.put(
        "/users/me/favorites/aparcamientos:1903",
        headers=auth_headers("bob"),
    )

    alice = seeded_client.get(
        "/users/me/favorites",
        headers=auth_headers("alice"),
    ).json()
    bob = seeded_client.get(
        "/users/me/favorites",
        headers=auth_headers("bob"),
    ).json()

    assert [place["id"] for place in alice] == ["aparcamientos_en_linea:5500"]
    assert [place["id"] for place in bob] == ["aparcamientos:1903"]


def test_get_favorites_401_when_no_bearer_token(seeded_client):
    response = seeded_client.get("/users/me/favorites")

    assert response.status_code == 401


def test_get_favorites_accepts_x_session_token_alias(seeded_client, auth_headers):
    bearer = auth_headers("alice")["Authorization"].split(" ", 1)[1]

    response = seeded_client.get(
        "/users/me/favorites",
        headers={"X-Session-Token": bearer},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_favorites_skips_orphan_entries_silently(
    seeded_client, fake_redis, auth_headers
):
    headers = auth_headers("alice")

    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)
    seeded_client.put("/users/me/favorites/aparcamientos:1903", headers=headers)

    fake_redis.delete("parking:aparcamientos_en_linea:5500")

    response = seeded_client.get("/users/me/favorites", headers=headers)

    assert response.status_code == 200

    ids = [place["id"] for place in response.json()]
    assert ids == ["aparcamientos:1903"]


def test_full_favorite_lifecycle(seeded_client, freeze_time, auth_headers):
    headers = auth_headers("alice")

    seeded_client.put("/users/me/favorites/aparcamientos:1903", headers=headers)
    freeze_time(500)
    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)

    listing = seeded_client.get("/users/me/favorites", headers=headers).json()

    assert [place["id"] for place in listing] == [
        "aparcamientos_en_linea:5500",
        "aparcamientos:1903",
    ]

    delete = seeded_client.delete(
        "/users/me/favorites/aparcamientos:1903",
        headers=headers,
    )

    assert delete.json()["removed"] is True

    after = seeded_client.get("/users/me/favorites", headers=headers).json()

    assert [place["id"] for place in after] == ["aparcamientos_en_linea:5500"]


def test_openapi_contains_favorites_examples(seeded_client):
    schema = seeded_client.get("/openapi.json").json()
    paths = schema["paths"]

    list_resp = paths["/users/me/favorites"]["get"]["responses"]["200"]
    put_resp = paths["/users/me/favorites/{parking_id}"]["put"]["responses"]["200"]
    delete_resp = paths["/users/me/favorites/{parking_id}"]["delete"]["responses"]["200"]

    assert "example" in list_resp["content"]["application/json"]
    assert "example" in put_resp["content"]["application/json"]
    assert put_resp["content"]["application/json"]["example"]["created"] is True
    assert "example" in delete_resp["content"]["application/json"]
    assert delete_resp["content"]["application/json"]["example"]["removed"] is True


def test_favorites_cap_drops_oldest_when_max_reached(
    seeded_client, fake_redis, auth_headers, monkeypatch, freeze_time
):
    monkeypatch.setattr("app.routers.favorites.FAVORITES_MAX_PER_USER", 2)

    headers = auth_headers("capped-user")
    ids = [
        "aparcamientos:1903",
        "aparcamientos_en_linea:5500",
        "parkings:2001",
    ]

    for parking_id in ids:
        seeded_client.put(f"/users/me/favorites/{parking_id}", headers=headers)
        freeze_time(1000)

    bucket = fake_redis.zsets.get("user:capped-user:favorites", {})

    assert set(bucket.keys()) == {
        "aparcamientos_en_linea:5500",
        "parkings:2001",
    }

    listing = seeded_client.get("/users/me/favorites", headers=headers).json()

    assert "aparcamientos:1903" not in {place["id"] for place in listing}


def test_favorites_cap_disabled_when_zero(
    seeded_client, fake_redis, auth_headers, monkeypatch, freeze_time
):
    monkeypatch.setattr("app.routers.favorites.FAVORITES_MAX_PER_USER", 0)

    headers = auth_headers("uncapped-user")

    for parking_id in (
        "aparcamientos:1903",
        "aparcamientos_en_linea:5500",
        "parkings:2001",
    ):
        seeded_client.put(f"/users/me/favorites/{parking_id}", headers=headers)
        freeze_time(1000)

    bucket = fake_redis.zsets.get("user:uncapped-user:favorites", {})

    assert len(bucket) == 3