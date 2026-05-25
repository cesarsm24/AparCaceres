"""Tests del proxy de fotos.

Cubren la ruta optimizada de miniaturas para evitar regresiones en la caché
local que usa Flutter en listados y mapas.
"""

from __future__ import annotations

import io

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.routers import photos as photos_router

_SIG_PHOTO_URL = "https://sig.caceres.es/fotosOriginales/TOPONIMIA/test.jpg"


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 240), (20, 80, 140)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(photos_router.router)
    return TestClient(app)


def test_photo_proxy_generates_and_reuses_thumb_cache(tmp_path, monkeypatch):
    calls: list[str] = []

    async def fake_fetch(target: str) -> httpx.Response:
        calls.append(target)
        return httpx.Response(
            200,
            content=_image_bytes(),
            headers={"content-type": "image/jpeg"},
        )

    monkeypatch.setattr(photos_router, "PHOTO_PROXY_CACHE_DIR", tmp_path)
    monkeypatch.setattr(photos_router, "PHOTO_THUMBNAIL_MAX_SIZE", 48)
    monkeypatch.setattr(photos_router, "_fetch_upstream_image", fake_fetch)

    client = _client()

    first = client.get("/photo-proxy", params={"u": _SIG_PHOTO_URL, "size": "thumb"})
    second = client.get("/photo-proxy", params={"u": _SIG_PHOTO_URL, "size": "thumb"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["content-type"].startswith("image/jpeg")
    assert second.content == first.content
    assert calls == [_SIG_PHOTO_URL]
    assert len(list(tmp_path.glob("*.jpg"))) == 1


def test_photo_proxy_keeps_original_mode_without_thumbnail_cache(tmp_path, monkeypatch):
    async def fake_fetch(_target: str) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"original-image",
            headers={"content-type": "image/jpeg", "content-length": "14"},
        )

    monkeypatch.setattr(photos_router, "PHOTO_PROXY_CACHE_DIR", tmp_path)
    monkeypatch.setattr(photos_router, "_fetch_upstream_image", fake_fetch)

    response = _client().get("/photo-proxy", params={"u": _SIG_PHOTO_URL})

    assert response.status_code == 200
    assert response.content == b"original-image"
    assert response.headers["content-type"] == "image/jpeg"
    assert list(tmp_path.iterdir()) == []
