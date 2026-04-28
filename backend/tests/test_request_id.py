"""Tests de correlación de peticiones y logging JSON.

Verifican que el middleware propaga o genera `X-Request-ID` y que el formatter
estructura registros con identificador de petición y campos extra.
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestIdMiddleware,
    _request_id_ctx,
    configure_logging,
)


@pytest.fixture
def app_with_middleware() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    def _ping():
        return {"request_id": _request_id_ctx.get()}

    return TestClient(app)


def test_generates_request_id_when_absent(app_with_middleware):
    response = app_with_middleware.get("/ping")

    assert response.status_code == 200

    request_id = response.headers[REQUEST_ID_HEADER]

    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    assert response.json()["request_id"] == request_id


def test_respects_incoming_request_id(app_with_middleware):
    incoming = "trace-abc-123"

    response = app_with_middleware.get(
        "/ping",
        headers={REQUEST_ID_HEADER: incoming},
    )

    assert response.headers[REQUEST_ID_HEADER] == incoming
    assert response.json()["request_id"] == incoming


def test_request_id_resets_between_requests(app_with_middleware):
    first = app_with_middleware.get("/ping").headers[REQUEST_ID_HEADER]
    second = app_with_middleware.get("/ping").headers[REQUEST_ID_HEADER]

    assert first != second


def test_json_formatter_emits_request_id_and_extras():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="testlog",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.user_id = "u-42"

    token = _request_id_ctx.set("rid-xyz")
    try:
        line = formatter.format(record)
    finally:
        _request_id_ctx.reset(token)

    payload = json.loads(line)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "testlog"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "rid-xyz"
    assert payload["user_id"] == "u-42"


def test_configure_logging_is_idempotent():
    configure_logging("INFO")
    initial_count = len(logging.getLogger().handlers)

    configure_logging("INFO")

    assert len(logging.getLogger().handlers) == initial_count