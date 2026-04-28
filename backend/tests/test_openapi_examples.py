"""Tests de ejemplos OpenAPI publicados por los routers.

Validan que los ejemplos sean compatibles con sus modelos de respuesta y que
el esquema OpenAPI exponga los mismos payloads documentados en los routers.
"""

from __future__ import annotations

from app.enums import ParkingCategory
from app.routers.auth import _SESSION_RESPONSE_EXAMPLE, SessionResponse
from app.routers.favorites import (
    _FAVORITE_ADDED_EXAMPLE,
    _FAVORITE_REMOVED_EXAMPLE,
    _FAVORITES_LIST_EXAMPLE,
)
from app.routers.imports import _IMPORT_RESPONSE_EXAMPLE
from app.routers.parkings import (
    _CATEGORIES_EXAMPLE,
    _FACETS_EXAMPLE,
    _LIST_ENVELOPE_EXAMPLE,
    _NEARBY_ENVELOPE_EXAMPLE,
    _PLACE_NEARBY_EXAMPLE,
    _PLACE_POINT_EXAMPLE,
    _PLACE_POLYGON_EXAMPLE,
)
from app.schemas import (
    FavoriteAdded,
    FavoriteRemoved,
    ParkingFacetsOut,
    ParkingPlaceNearbyOut,
    ParkingPlaceOut,
    ParkingPlacesEnvelopeOut,
    ParkingPlacesNearbyEnvelopeOut,
)
from main import app


def _drop_nones(value):
    """Elimina valores nulos para comparar con el schema generado por FastAPI."""
    if isinstance(value, dict):
        return {key: _drop_nones(item) for key, item in value.items() if item is not None}

    if isinstance(value, list):
        return [_drop_nones(item) for item in value]

    return value


def test_example_payloads_validate_against_response_models():
    ParkingPlaceOut.model_validate(_PLACE_POINT_EXAMPLE)
    ParkingPlaceOut.model_validate(_PLACE_POLYGON_EXAMPLE)
    ParkingPlaceNearbyOut.model_validate(_PLACE_NEARBY_EXAMPLE)
    ParkingPlacesEnvelopeOut.model_validate(_LIST_ENVELOPE_EXAMPLE)
    ParkingPlacesNearbyEnvelopeOut.model_validate(_NEARBY_ENVELOPE_EXAMPLE)
    ParkingFacetsOut.model_validate(_FACETS_EXAMPLE)
    FavoriteAdded.model_validate(_FAVORITE_ADDED_EXAMPLE)
    FavoriteRemoved.model_validate(_FAVORITE_REMOVED_EXAMPLE)
    SessionResponse.model_validate(_SESSION_RESPONSE_EXAMPLE)

    for item in _FAVORITES_LIST_EXAMPLE:
        ParkingPlaceOut.model_validate(item)


def test_import_example_contains_actual_response_keys():
    assert _IMPORT_RESPONSE_EXAMPLE.keys() == {
        "status",
        "imported",
        "skipped",
        "search_index",
        "ids_disambiguated",
        "photos_resolved",
        "cache_version",
        "files_processed",
        "files_skipped",
        "sources",
    }


def test_openapi_schema_exposes_the_same_examples():
    schema = app.openapi()

    assert (
        schema["paths"]["/auth/session"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_SESSION_RESPONSE_EXAMPLE)
    )
    assert (
        schema["paths"]["/import-parkings"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_IMPORT_RESPONSE_EXAMPLE)
    )
    assert (
        schema["paths"]["/users/me/favorites"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_FAVORITES_LIST_EXAMPLE)
    )
    assert (
        schema["paths"]["/users/me/favorites/{parking_id}"]["put"]["responses"]["200"][
            "content"
        ]["application/json"]["example"]
        == _drop_nones(_FAVORITE_ADDED_EXAMPLE)
    )
    assert (
        schema["paths"]["/users/me/favorites/{parking_id}"]["delete"]["responses"]["200"][
            "content"
        ]["application/json"]["example"]
        == _drop_nones(_FAVORITE_REMOVED_EXAMPLE)
    )
    assert (
        schema["paths"]["/parkings"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_LIST_ENVELOPE_EXAMPLE)
    )
    assert (
        schema["paths"]["/parkings/nearby"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_NEARBY_ENVELOPE_EXAMPLE)
    )
    assert (
        schema["paths"]["/parkings/in-bounds"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_LIST_ENVELOPE_EXAMPLE)
    )
    assert (
        schema["paths"]["/parkings/categories"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_CATEGORIES_EXAMPLE)
    )
    assert (
        schema["paths"]["/parkings/facets"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_FACETS_EXAMPLE)
    )
    assert (
        schema["paths"]["/parkings/{parking_id}"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        == _drop_nones(_PLACE_POLYGON_EXAMPLE)
    )


def test_categories_example_contains_known_enum_values():
    assert all(
        category in {item.value for item in ParkingCategory}
        for category in _CATEGORIES_EXAMPLE
    )