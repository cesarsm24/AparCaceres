"""Tests HTTP de los endpoints `/users/me/favorites*`.

Comparten `seeded_client` con los tests de parkings (mismo dataset sintético
ya importado) y monkeypatchean `_now_ms` en `app.routers.favorites` para fijar
el orden temporal sin depender del reloj real.

Cubren:
- Alta (PUT) con payload, idempotencia y conservación de `addedAt`.
- Baja (DELETE) con flag `removed` y casuística "no estaba".
- Listado (GET) con shape completo de `ParkingPlace` y orden newest-first.
- Validación de cabecera `X-User-Id` (400) y de aparcamiento inexistente (404).
- Aislamiento entre usuarios.
- Favoritos huérfanos (parking borrado del catálogo): se filtran del GET.
- OpenAPI: ejemplos registrados para los 3 endpoints.
"""

from __future__ import annotations

import pytest

# Mismas claves obligatorias que usa el test del catálogo: el GET de favoritos
# devuelve `ParkingPlace` y el cliente Flutter reusa `ParkingPlace.fromJson`,
# así que el shape tiene que ser idéntico al de `/parkings`.
_REQUIRED_PLACE_FIELDS = {
    "id", "name", "category", "vehicleType", "regulation",
    "geometryType", "latitude", "longitude", "coordinates",
    "totalSpaces", "streetName", "streetType", "district",
    "neighborhood", "sourceDataset", "imageUrl", "urlFicha",
    "urlVia", "management",
}


def _assert_place_shape(place: dict) -> None:
    assert _REQUIRED_PLACE_FIELDS.issubset(place.keys()), (
        f"Faltan campos: {_REQUIRED_PLACE_FIELDS - place.keys()}"
    )


@pytest.fixture
def freeze_time(monkeypatch):
    """Permite fijar `_now_ms` desde un test (avanzando manualmente).

    Devuelve una función `tick(ms)` que adelanta el reloj `ms` milisegundos
    desde el inicio del test (epoch fijo en 1_700_000_000_000 → 2023-11-14).
    """
    state = {"now_ms": 1_700_000_000_000}

    def fake_now() -> int:
        return state["now_ms"]

    monkeypatch.setattr("app.routers.favorites._now_ms", fake_now)

    def tick(delta_ms: int) -> int:
        state["now_ms"] += delta_ms
        return state["now_ms"]

    return tick


# ============================================================
# PUT /users/me/favorites/{parkingId}
# ============================================================

def test_put_favorite_creates_entry_and_returns_payload(seeded_client):
    response = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"X-User-Id": "alice"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "aparcamientos_en_linea:5500"
    assert body["created"] is True
    # `addedAt` debe ser un ISO 8601 UTC (no validamos exacto: solo el formato).
    assert body["addedAt"].endswith("+00:00")


def test_put_favorite_is_idempotent_keeps_added_at(seeded_client, freeze_time):
    headers = {"X-User-Id": "alice"}

    first = seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)
    assert first.json()["created"] is True
    original_added_at = first.json()["addedAt"]

    # Avanzamos el reloj un buen rato; el segundo PUT no debe reescribir el score.
    freeze_time(60_000)

    second = seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["addedAt"] == original_added_at


def test_put_favorite_404_when_parking_does_not_exist(seeded_client):
    response = seeded_client.put(
        "/users/me/favorites/no-existe",
        headers={"X-User-Id": "alice"},
    )
    assert response.status_code == 404
    assert "no-existe" in response.json()["detail"]


def test_put_favorite_400_when_x_user_id_missing(seeded_client):
    response = seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500")
    assert response.status_code == 400
    assert "X-User-Id" in response.json()["detail"]


def test_put_favorite_400_when_x_user_id_blank(seeded_client):
    response = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"X-User-Id": "   "},
    )
    assert response.status_code == 400


def test_put_favorite_400_when_x_user_id_has_forbidden_chars(seeded_client):
    # ":" rompería la convención de claves Redis user:{id}:favorites.
    response = seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"X-User-Id": "ali:ce"},
    )
    assert response.status_code == 400


# ============================================================
# DELETE /users/me/favorites/{parkingId}
# ============================================================

def test_delete_favorite_removes_existing_entry(seeded_client):
    headers = {"X-User-Id": "alice"}
    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)

    response = seeded_client.delete(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"id": "aparcamientos_en_linea:5500", "removed": True}

    # Tras el DELETE, el GET ya no lo trae.
    listing = seeded_client.get("/users/me/favorites", headers=headers).json()
    assert listing == []


def test_delete_favorite_returns_removed_false_when_not_in_list(seeded_client):
    response = seeded_client.delete(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"X-User-Id": "alice"},
    )
    # El parking existe pero no estaba en favoritos: 200, removed=False.
    assert response.status_code == 200
    assert response.json() == {"id": "aparcamientos_en_linea:5500", "removed": False}


def test_delete_favorite_404_when_parking_does_not_exist(seeded_client):
    response = seeded_client.delete(
        "/users/me/favorites/no-existe",
        headers={"X-User-Id": "alice"},
    )
    assert response.status_code == 404


def test_delete_favorite_400_when_x_user_id_missing(seeded_client):
    response = seeded_client.delete("/users/me/favorites/aparcamientos_en_linea:5500")
    assert response.status_code == 400


# ============================================================
# GET /users/me/favorites
# ============================================================

def test_get_favorites_empty_when_user_has_none(seeded_client):
    response = seeded_client.get(
        "/users/me/favorites",
        headers={"X-User-Id": "alice"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_favorites_returns_full_parking_place_shape(seeded_client):
    headers = {"X-User-Id": "alice"}
    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)

    response = seeded_client.get("/users/me/favorites", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    _assert_place_shape(body[0])
    assert body[0]["id"] == "aparcamientos_en_linea:5500"
    assert body[0]["name"] == "Calle Dalia"
    assert body[0]["totalSpaces"] == 16
    # POLYGON: el coordinates debe sobrevivir al round-trip por Redis.
    assert body[0]["geometryType"] == "polygon"
    assert body[0]["coordinates"][0][0] == [-6.3994515, 39.4670139]


def test_get_favorites_orders_by_most_recent_first(seeded_client, freeze_time):
    headers = {"X-User-Id": "alice"}

    # Tres favoritos añadidos con 1s entre cada uno.
    seeded_client.put("/users/me/favorites/aparcamientos:1903", headers=headers)
    freeze_time(1_000)
    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)
    freeze_time(1_000)
    seeded_client.put("/users/me/favorites/parking_motos_puntos:9100", headers=headers)

    response = seeded_client.get("/users/me/favorites", headers=headers)
    ids = [p["id"] for p in response.json()]
    assert ids == ["parking_motos_puntos:9100", "aparcamientos_en_linea:5500", "aparcamientos:1903"]


def test_get_favorites_isolated_per_user(seeded_client):
    seeded_client.put(
        "/users/me/favorites/aparcamientos_en_linea:5500",
        headers={"X-User-Id": "alice"},
    )
    seeded_client.put(
        "/users/me/favorites/aparcamientos:1903",
        headers={"X-User-Id": "bob"},
    )

    alice = seeded_client.get(
        "/users/me/favorites", headers={"X-User-Id": "alice"}
    ).json()
    bob = seeded_client.get(
        "/users/me/favorites", headers={"X-User-Id": "bob"}
    ).json()

    assert [p["id"] for p in alice] == ["aparcamientos_en_linea:5500"]
    assert [p["id"] for p in bob] == ["aparcamientos:1903"]


def test_get_favorites_400_when_x_user_id_missing(seeded_client):
    response = seeded_client.get("/users/me/favorites")
    assert response.status_code == 400


def test_get_favorites_skips_orphan_entries_silently(
    seeded_client, fake_redis
):
    """Si un favorito apunta a un parking borrado del catálogo, GET lo omite."""
    headers = {"X-User-Id": "alice"}

    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)
    seeded_client.put("/users/me/favorites/aparcamientos:1903", headers=headers)

    # Simulamos que el catálogo pierde uno de los aparcamientos (p. ej. tras
    # un re-import del dataset municipal). El favorito queda huérfano.
    fake_redis.delete("parking:aparcamientos_en_linea:5500")

    response = seeded_client.get("/users/me/favorites", headers=headers)
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert ids == ["aparcamientos:1903"]  # 5500 desaparece del listado


# ============================================================
# Flujo combinado: put -> get -> delete -> get
# ============================================================

def test_full_favorite_lifecycle(seeded_client, freeze_time):
    headers = {"X-User-Id": "alice"}

    seeded_client.put("/users/me/favorites/aparcamientos:1903", headers=headers)
    freeze_time(500)
    seeded_client.put("/users/me/favorites/aparcamientos_en_linea:5500", headers=headers)

    listing = seeded_client.get("/users/me/favorites", headers=headers).json()
    assert [p["id"] for p in listing] == [
        "aparcamientos_en_linea:5500",
        "aparcamientos:1903",
    ]

    delete = seeded_client.delete(
        "/users/me/favorites/aparcamientos:1903", headers=headers
    )
    assert delete.json()["removed"] is True

    after = seeded_client.get("/users/me/favorites", headers=headers).json()
    assert [p["id"] for p in after] == ["aparcamientos_en_linea:5500"]


# ============================================================
# OpenAPI: examples registrados para los 3 endpoints
# ============================================================

def test_openapi_contains_favorites_examples(seeded_client):
    schema = seeded_client.get("/openapi.json").json()
    paths = schema["paths"]

    list_resp = paths["/users/me/favorites"]["get"]["responses"]["200"]
    assert "example" in list_resp["content"]["application/json"]

    put_resp = paths["/users/me/favorites/{parking_id}"]["put"]["responses"]["200"]
    assert "example" in put_resp["content"]["application/json"]
    assert put_resp["content"]["application/json"]["example"]["created"] is True

    delete_resp = paths["/users/me/favorites/{parking_id}"]["delete"]["responses"]["200"]
    assert "example" in delete_resp["content"]["application/json"]
    assert delete_resp["content"]["application/json"]["example"]["removed"] is True
