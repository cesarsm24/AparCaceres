"""Tests HTTP de los endpoints `/parkings*`.

Usan `seeded_client` (fixture de `conftest.py`): un `TestClient` de FastAPI
contra una app con `FakeRedis` ya alimentada por `run_import` con un dataset
sintético que cubre los 3 tipos de geometría y variedad de enums.

Foco:
- Shape de las respuestas == lo que consume `ParkingPlace.fromJson`.
- Filtros (`q`, `ids`, `vehicleType`, `category`, `regulation`, `minSpaces`)
  con la misma semántica que el cliente Flutter.
- Geometrías point / polygon / line_string viajan correctamente.
- Caché de `/nearby` activa solo sin filtros (`X-Cache: HIT|MISS|BYPASS`).
- Alias legacy `radius` reconocido como sinónimo de `radiusMeters`.
- 404 en detalle inexistente.
"""

from __future__ import annotations

# Campos que deben estar SIEMPRE presentes en la respuesta para que
# `ParkingPlace.fromJson` no rompa.
_REQUIRED_PLACE_FIELDS = {
    "id", "name", "category", "vehicleType", "regulation",
    "geometryType", "latitude", "longitude", "coordinates",
    "totalSpaces", "streetName", "streetType", "district",
    "neighborhood", "sourceDataset", "imageUrl", "urlFicha",
    "urlVia", "management",
}


def _assert_place_shape(place: dict) -> None:
    """Comprueba que el dict trae todas las claves del contrato móvil."""
    assert _REQUIRED_PLACE_FIELDS.issubset(place.keys()), (
        f"Faltan campos: {_REQUIRED_PLACE_FIELDS - place.keys()}"
    )


# ============================================================
# GET /parkings
# ============================================================

def test_list_parkings_returns_full_catalog_with_contract_shape(seeded_client):
    response = seeded_client.get("/parkings")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    # El dataset sintético tiene 7 places (todos con mslink).
    assert len(body) == 7
    for place in body:
        _assert_place_shape(place)


def test_list_parkings_filters_by_q_accent_insensitive(seeded_client):
    response = seeded_client.get("/parkings", params={"q": "politecnica"})
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Escuela Politécnica"]


def test_list_parkings_q_matches_street_and_district_fields(seeded_client):
    # "centro" aparece en district/neighborhood de Obispo Galarza y en district
    # de Calle Colon.
    response = seeded_client.get("/parkings", params={"q": "centro"})
    ids = sorted(p["id"] for p in response.json())
    assert ids == ["aparcamiento-2001", "aparcamiento-9200"]


def test_list_parkings_filters_by_repeated_vehicle_type(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("vehicleType", "bike"), ("vehicleType", "motorbike")],
    )
    assert response.status_code == 200
    cats = sorted(p["category"] for p in response.json())
    assert cats == ["bicycle", "motorbike"]


def test_list_parkings_filters_by_repeated_category(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("category", "paid_parking"), ("category", "blue_zone")],
    )
    ids = sorted(p["id"] for p in response.json())
    assert ids == ["aparcamiento-2001", "aparcamiento-9001"]


def test_list_parkings_filters_by_regulation(seeded_client):
    response = seeded_client.get("/parkings", params={"regulation": "paid"})
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "aparcamiento-2001"


def test_list_parkings_filters_by_min_spaces_drops_unknown(seeded_client):
    response = seeded_client.get("/parkings", params={"minSpaces": 10})
    ids = sorted(p["id"] for p in response.json())
    # Quedan los que tienen >= 10 plazas: Dalia (16), Ledesma (19), Londres (15).
    assert ids == ["aparcamiento-5500", "aparcamiento-9001", "aparcamiento-9100"]


def test_list_parkings_filters_by_repeated_ids(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("ids", "aparcamiento-1903"), ("ids", "aparcamiento-7700")],
    )
    ids = sorted(p["id"] for p in response.json())
    assert ids == ["aparcamiento-1903", "aparcamiento-7700"]


def test_list_parkings_ids_with_unknown_id_returns_only_known(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("ids", "aparcamiento-1903"), ("ids", "no-existe")],
    )
    ids = [p["id"] for p in response.json()]
    assert ids == ["aparcamiento-1903"]


def test_list_parkings_combines_filters_as_and(seeded_client):
    # category=street_line AND minSpaces=10 -> solo Calle Dalia (16),
    # descarta Esquiladores (sin totalSpaces).
    response = seeded_client.get(
        "/parkings",
        params={"category": "street_line", "minSpaces": 10},
    )
    ids = [p["id"] for p in response.json()]
    assert ids == ["aparcamiento-5500"]


def test_list_parkings_invalid_enum_returns_422(seeded_client):
    response = seeded_client.get("/parkings", params={"vehicleType": "spaceship"})
    assert response.status_code == 422


def test_list_parkings_polygon_coordinates_round_trip(seeded_client):
    response = seeded_client.get("/parkings", params={"ids": "aparcamiento-5500"})
    place = response.json()[0]
    assert place["geometryType"] == "polygon"
    assert place["coordinates"][0][0] == [-6.3994515, 39.4670139]
    assert place["totalSpaces"] == 16


def test_list_parkings_line_string_coordinates_round_trip(seeded_client):
    response = seeded_client.get("/parkings", params={"ids": "aparcamiento-7700"})
    place = response.json()[0]
    assert place["geometryType"] == "line_string"
    assert place["coordinates"] == [
        [-6.4022597, 39.4775947],
        [-6.4022522, 39.4775983],
        [-6.4022077, 39.4776199],
    ]


def test_list_parkings_point_has_null_coordinates(seeded_client):
    response = seeded_client.get("/parkings", params={"ids": "aparcamiento-1903"})
    place = response.json()[0]
    assert place["geometryType"] == "point"
    assert place["coordinates"] is None


# ============================================================
# GET /parkings/nearby
# ============================================================

def test_nearby_returns_distance_and_orders_by_proximity(seeded_client):
    # Centro aproximado de Cáceres; radio amplio para incluir todo.
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 5000},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"

    body = response.json()
    assert len(body) >= 5
    for place in body:
        _assert_place_shape(place)
        assert "distanceMeters" in place
        assert place["distanceMeters"] >= 0

    # Debe venir ordenado ascendente por distancia.
    distances = [p["distanceMeters"] for p in body]
    assert distances == sorted(distances)


def test_nearby_default_radius_is_1000_meters(seeded_client):
    # Sin pasar radio.
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724},
    )
    assert response.status_code == 200
    for place in response.json():
        assert place["distanceMeters"] <= 1000


def test_nearby_legacy_radius_alias_still_works(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radius": 200},
    )
    assert response.status_code == 200
    for place in response.json():
        assert place["distanceMeters"] <= 200


def test_nearby_radius_meters_takes_precedence_over_radius(seeded_client):
    # Si pasan ambos, gana radiusMeters (más explícito).
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 200, "radius": 5000},
    )
    for place in response.json():
        assert place["distanceMeters"] <= 200


def test_nearby_applies_category_filter(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={
            "lat": 39.4753,
            "lng": -6.3724,
            "radiusMeters": 10000,
            "category": "bicycle",
        },
    )
    body = response.json()
    assert len(body) == 1
    assert body[0]["category"] == "bicycle"


def test_nearby_applies_q_filter(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 10000, "q": "dalia"},
    )
    names = [p["name"] for p in response.json()]
    assert names == ["Calle Dalia"]


def test_nearby_caches_when_no_filters_applied(seeded_client):
    base = {"lat": 39.4753, "lng": -6.3724, "radiusMeters": 800}

    first = seeded_client.get("/parkings/nearby", params=base)
    assert first.headers.get("X-Cache") == "MISS"

    second = seeded_client.get("/parkings/nearby", params=base)
    assert second.headers.get("X-Cache") == "HIT"
    # Mismo payload literal.
    assert second.json() == first.json()


def test_nearby_bypasses_cache_when_filters_applied(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 800, "category": "parking"},
    )
    assert response.headers.get("X-Cache") == "BYPASS"


def test_nearby_returns_empty_when_outside_any_radius(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 0.0, "lng": 0.0, "radiusMeters": 100},
    )
    assert response.json() == []


# ============================================================
# GET /parkings/{id}
# ============================================================

def test_get_parking_by_id_returns_full_contract(seeded_client):
    response = seeded_client.get("/parkings/aparcamiento-5500")
    assert response.status_code == 200
    place = response.json()
    _assert_place_shape(place)
    assert place["id"] == "aparcamiento-5500"
    assert place["name"] == "Calle Dalia"
    assert place["totalSpaces"] == 16


def test_get_parking_by_id_404_when_missing(seeded_client):
    response = seeded_client.get("/parkings/no-existe")
    assert response.status_code == 404


def test_get_parking_by_id_does_not_collide_with_subroutes(seeded_client):
    # Si el routing fuese incorrecto, "nearby" o "categories" caerían aquí.
    nearby = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724},
    )
    categories = seeded_client.get("/parkings/categories")
    assert nearby.status_code == 200
    assert categories.status_code == 200


# ============================================================
# GET /parkings/categories
# ============================================================

def test_categories_returns_only_present_in_dataset_ordered(seeded_client):
    response = seeded_client.get("/parkings/categories")
    assert response.status_code == 200
    cats = response.json()
    # El dataset incluye: parking, paid_parking, street_line, blue_zone,
    # motorbike, bicycle. NO incluye street_battery, accessible, loading.
    assert cats == [
        "parking",
        "paid_parking",
        "street_line",
        "blue_zone",
        "motorbike",
        "bicycle",
    ]


def test_categories_empty_catalog_returns_empty_list(api_client):
    response = api_client.get("/parkings/categories")
    assert response.status_code == 200
    assert response.json() == []


# ============================================================
# OpenAPI: examples deben quedar registrados en /openapi.json
# ============================================================

def test_openapi_contains_examples_for_each_endpoint(seeded_client):
    schema = seeded_client.get("/openapi.json").json()
    paths = schema["paths"]

    # GET /parkings
    list_response = paths["/parkings"]["get"]["responses"]["200"]
    assert "example" in list_response["content"]["application/json"]

    # GET /parkings/nearby
    nearby_response = paths["/parkings/nearby"]["get"]["responses"]["200"]
    assert "example" in nearby_response["content"]["application/json"]
    assert "distanceMeters" in (
        nearby_response["content"]["application/json"]["example"][0]
    )

    # GET /parkings/categories
    cats_response = paths["/parkings/categories"]["get"]["responses"]["200"]
    assert "example" in cats_response["content"]["application/json"]

    # GET /parkings/{parking_id}
    detail_response = paths["/parkings/{parking_id}"]["get"]["responses"]["200"]
    assert "example" in detail_response["content"]["application/json"]
