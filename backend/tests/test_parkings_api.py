"""Tests HTTP de endpoints de aparcamientos.

Verifican el contrato público de respuestas, filtros de catálogo, geometrías,
caché de búsquedas cercanas, paginación, facets y ejemplos OpenAPI.
"""

from __future__ import annotations

_REQUIRED_PLACE_FIELDS = {
    "id", "name", "category", "vehicleType", "regulation",
    "geometryType", "latitude", "longitude", "coordinates",
    "totalSpaces", "streetName", "streetType", "district",
    "neighborhood", "sourceDataset", "imageUrl", "urlFicha",
    "urlVia", "management",
}


def _assert_place_shape(place: dict) -> None:
    """Comprueba que un aparcamiento contiene todas las claves públicas."""
    assert _REQUIRED_PLACE_FIELDS.issubset(place.keys()), (
        f"Faltan campos: {_REQUIRED_PLACE_FIELDS - place.keys()}"
    )


def _items(response) -> list[dict]:
    """Extrae los elementos de un envelope paginado."""
    body = response.json()

    assert set(body.keys()) == {"items", "total", "limit", "offset", "truncated", "facets"}
    assert isinstance(body["items"], list)

    return body["items"]


def test_list_parkings_returns_full_catalog_with_contract_shape(seeded_client):
    response = seeded_client.get("/parkings")

    assert response.status_code == 200

    body = response.json()

    assert isinstance(body, dict)
    assert body["total"] == 7
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert body["truncated"] is False
    assert len(body["items"]) == 7

    for place in body["items"]:
        _assert_place_shape(place)


def test_list_parkings_filters_by_q_accent_insensitive(seeded_client):
    response = seeded_client.get("/parkings", params={"q": "politecnica"})

    assert response.status_code == 200

    names = [place["name"] for place in _items(response)]

    assert names == ["Escuela Politécnica"]


def test_list_parkings_q_matches_street_and_district_fields(seeded_client):
    response = seeded_client.get("/parkings", params={"q": "centro"})
    ids = sorted(place["id"] for place in _items(response))

    assert ids == ["parking_bicis:9200", "parkings:2001"]


def test_list_parkings_filters_by_repeated_vehicle_type(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("vehicleType", "bike"), ("vehicleType", "motorbike")],
    )

    assert response.status_code == 200

    categories = sorted(place["category"] for place in _items(response))

    assert categories == ["bicycle", "motorbike"]


def test_list_parkings_filters_by_repeated_category(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("category", "paid_parking"), ("category", "blue_zone")],
    )
    ids = sorted(place["id"] for place in _items(response))

    assert ids == ["parkings:2001", "zona_azul:9001"]


def test_list_parkings_filters_by_regulation(seeded_client):
    response = seeded_client.get("/parkings", params={"regulation": "paid"})
    body = _items(response)

    assert len(body) == 1
    assert body[0]["id"] == "parkings:2001"


def test_list_parkings_filters_by_min_spaces_drops_unknown(seeded_client):
    response = seeded_client.get("/parkings", params={"minSpaces": 10})
    ids = sorted(place["id"] for place in _items(response))

    assert ids == [
        "aparcamientos_en_linea:5500",
        "parking_motos_puntos:9100",
        "zona_azul:9001",
    ]


def test_list_parkings_filters_by_repeated_ids(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("ids", "aparcamientos:1903"), ("ids", "aparcamientos_en_linea:7700")],
    )
    ids = sorted(place["id"] for place in _items(response))

    assert ids == ["aparcamientos:1903", "aparcamientos_en_linea:7700"]


def test_list_parkings_ids_with_unknown_id_returns_only_known(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params=[("ids", "aparcamientos:1903"), ("ids", "no-existe")],
    )
    ids = [place["id"] for place in _items(response)]

    assert ids == ["aparcamientos:1903"]


def test_list_parkings_combines_filters_as_and(seeded_client):
    response = seeded_client.get(
        "/parkings",
        params={"category": "street_line", "minSpaces": 10},
    )
    ids = [place["id"] for place in _items(response)]

    assert ids == ["aparcamientos_en_linea:5500"]


def test_list_parkings_invalid_enum_returns_422(seeded_client):
    response = seeded_client.get("/parkings", params={"vehicleType": "spaceship"})

    assert response.status_code == 422


def test_list_parkings_polygon_coordinates_round_trip(seeded_client):
    response = seeded_client.get("/parkings", params={"ids": "aparcamientos_en_linea:5500"})
    place = _items(response)[0]

    assert place["geometryType"] == "polygon"
    assert place["coordinates"][0][0] == [-6.3994515, 39.4670139]
    assert place["totalSpaces"] == 16


def test_list_parkings_line_string_coordinates_round_trip(seeded_client):
    response = seeded_client.get("/parkings", params={"ids": "aparcamientos_en_linea:7700"})
    place = _items(response)[0]

    assert place["geometryType"] == "line_string"
    assert place["coordinates"] == [
        [-6.4022597, 39.4775947],
        [-6.4022522, 39.4775983],
        [-6.4022077, 39.4776199],
    ]


def test_list_parkings_point_has_null_coordinates(seeded_client):
    response = seeded_client.get("/parkings", params={"ids": "aparcamientos:1903"})
    place = _items(response)[0]

    assert place["geometryType"] == "point"
    assert place["coordinates"] is None


def test_list_parkings_envelope_supports_limit_and_offset(seeded_client):
    response = seeded_client.get("/parkings", params={"limit": 2, "offset": 1})

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 7
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert body["truncated"] is True
    assert len(body["items"]) == 2
    assert response.headers["X-Total-Count"] == "7"
    assert response.headers["X-Limit"] == "2"
    assert response.headers["X-Offset"] == "1"


def test_list_parkings_can_include_global_facets(seeded_client):
    response = seeded_client.get("/parkings", params={"includeFacets": "true"})

    assert response.status_code == 200

    facets = response.json()["facets"]

    assert facets["total"] == 7
    assert facets["categories"]["street_line"] == 2
    assert facets["vehicleTypes"]["bike"] == 1
    assert facets["datasets"]["aparcamientos_en_linea"] == 2


def test_nearby_returns_distance_and_orders_by_proximity(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 5000},
    )

    assert response.status_code == 200
    assert response.headers.get("X-Cache") == "MISS"

    body = _items(response)

    assert len(body) >= 5

    for place in body:
        _assert_place_shape(place)
        assert "distanceMeters" in place
        assert place["distanceMeters"] >= 0

    distances = [place["distanceMeters"] for place in body]

    assert distances == sorted(distances)


def test_nearby_default_radius_is_1000_meters(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724},
    )

    assert response.status_code == 200

    for place in _items(response):
        assert place["distanceMeters"] <= 1000


def test_nearby_legacy_radius_alias_still_works(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radius": 200},
    )

    assert response.status_code == 200

    for place in _items(response):
        assert place["distanceMeters"] <= 200


def test_nearby_radius_meters_takes_precedence_over_radius(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 200, "radius": 5000},
    )

    assert response.status_code == 200

    for place in _items(response):
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
    body = _items(response)

    assert len(body) == 1
    assert body[0]["category"] == "bicycle"


def test_nearby_applies_q_filter(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 10000, "q": "dalia"},
    )
    names = [place["name"] for place in _items(response)]

    assert names == ["Calle Dalia"]


def test_nearby_caches_when_no_filters_applied(seeded_client):
    base = {"lat": 39.4753, "lng": -6.3724, "radiusMeters": 800}

    first = seeded_client.get("/parkings/nearby", params=base)
    second = seeded_client.get("/parkings/nearby", params=base)

    assert first.headers.get("X-Cache") == "MISS"
    assert second.headers.get("X-Cache") == "HIT"
    assert second.json() == first.json()


def test_nearby_caches_low_cardinality_filters(seeded_client):
    base = {
        "lat": 39.4753,
        "lng": -6.3724,
        "radiusMeters": 800,
        "category": "parking",
    }

    first = seeded_client.get("/parkings/nearby", params=base)
    second = seeded_client.get("/parkings/nearby", params=base)

    assert first.headers.get("X-Cache") == "MISS"
    assert second.headers.get("X-Cache") == "HIT"
    assert second.json() == first.json()


def test_nearby_cache_key_is_filter_aware(seeded_client):
    base = {"lat": 39.4753, "lng": -6.3724, "radiusMeters": 800}

    no_filter = seeded_client.get("/parkings/nearby", params=base)
    with_filter = seeded_client.get(
        "/parkings/nearby",
        params={**base, "category": "blue_zone"},
    )

    assert no_filter.headers.get("X-Cache") == "MISS"
    assert with_filter.headers.get("X-Cache") == "MISS"


def test_nearby_bypasses_cache_for_text_search(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724, "radiusMeters": 800, "q": "dalia"},
    )

    assert response.headers.get("X-Cache") == "BYPASS"


def test_nearby_returns_empty_when_outside_any_radius(seeded_client):
    response = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 0.0, "lng": 0.0, "radiusMeters": 100},
    )

    assert _items(response) == []


def test_in_bounds_returns_only_places_inside_viewport(seeded_client):
    response = seeded_client.get(
        "/parkings/in-bounds",
        params={
            "minLat": 39.466,
            "minLng": -6.400,
            "maxLat": 39.467,
            "maxLng": -6.398,
        },
    )

    assert response.status_code == 200

    ids = [place["id"] for place in _items(response)]

    assert ids == ["aparcamientos_en_linea:5500"]


def test_in_bounds_rejects_invalid_bbox(seeded_client):
    response = seeded_client.get(
        "/parkings/in-bounds",
        params={
            "minLat": 39.48,
            "minLng": -6.40,
            "maxLat": 39.47,
            "maxLng": -6.39,
        },
    )

    assert response.status_code == 400


def test_get_parking_by_id_returns_full_contract(seeded_client):
    response = seeded_client.get("/parkings/aparcamientos_en_linea:5500")

    assert response.status_code == 200

    place = response.json()

    _assert_place_shape(place)

    assert place["id"] == "aparcamientos_en_linea:5500"
    assert place["name"] == "Calle Dalia"
    assert place["totalSpaces"] == 16


def test_get_parking_by_id_404_when_missing(seeded_client):
    response = seeded_client.get("/parkings/no-existe")

    assert response.status_code == 404


def test_get_parking_by_id_does_not_collide_with_subroutes(seeded_client):
    nearby = seeded_client.get(
        "/parkings/nearby",
        params={"lat": 39.4753, "lng": -6.3724},
    )
    categories = seeded_client.get("/parkings/categories")

    assert nearby.status_code == 200
    assert categories.status_code == 200


def test_categories_returns_only_present_in_dataset_ordered(seeded_client):
    response = seeded_client.get("/parkings/categories")

    assert response.status_code == 200
    assert response.json() == [
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


def test_facets_returns_counts_by_dimension(seeded_client):
    response = seeded_client.get("/parkings/facets")

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 7
    assert body["categories"]["parking"] == 1
    assert body["categories"]["street_line"] == 2
    assert body["vehicleTypes"]["car"] == 5
    assert body["vehicleTypes"]["motorbike"] == 1
    assert body["regulations"]["paid"] == 1
    assert body["datasets"]["parking_bicis"] == 1


def test_openapi_contains_examples_for_each_endpoint(seeded_client):
    schema = seeded_client.get("/openapi.json").json()
    paths = schema["paths"]

    list_response = paths["/parkings"]["get"]["responses"]["200"]
    nearby_response = paths["/parkings/nearby"]["get"]["responses"]["200"]
    cats_response = paths["/parkings/categories"]["get"]["responses"]["200"]
    detail_response = paths["/parkings/{parking_id}"]["get"]["responses"]["200"]

    assert "example" in list_response["content"]["application/json"]
    assert "example" in nearby_response["content"]["application/json"]
    assert "distanceMeters" in (
        nearby_response["content"]["application/json"]["example"]["items"][0]
    )
    assert "example" in cats_response["content"]["application/json"]
    assert "example" in detail_response["content"]["application/json"]


def test_nearby_cache_key_precision_adapts_to_radius():
    from app.routers.parkings import _build_nearby_cache_key

    big = _build_nearby_cache_key(
        version="0",
        lat=39.4753,
        lng=-6.3724,
        radius=1000,
    )
    small = _build_nearby_cache_key(
        version="0",
        lat=39.4753,
        lng=-6.3724,
        radius=10,
    )

    assert "39.4753:-6.3724:1000" in big
    assert "39.47530:-6.37240:10" in small


def test_nearby_cache_key_distinguishes_close_centers_for_small_radius():
    from app.routers.parkings import _build_nearby_cache_key

    first = _build_nearby_cache_key(version="0", lat=39.47530, lng=-6.37240, radius=5)
    second = _build_nearby_cache_key(version="0", lat=39.47535, lng=-6.37240, radius=5)

    assert first != second