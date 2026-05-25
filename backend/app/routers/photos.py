"""Proxy de imágenes del SIG para clientes web.

El SIG municipal sirve sus fotos en `https://sig.caceres.es/fotosOriginales/`
con dos limitaciones que rompen al cliente Flutter web:
  1. **Sin cabecera `Access-Control-Allow-Origin`**: el navegador bloquea
     las imágenes cuando la app no se sirve desde `sig.caceres.es`. En la
     versión Android/iOS nativa esto no aplica (sin XHR no hay CORS), pero
     sí en `flutter run -d chrome`.
  2. **Cert TLS por FNMT-RCM** (CA del gobierno español) que algunos
     bundles de raíz no incluyen. Igual que en el scraping del importer,
     deshabilitamos verify para no depender del bundle del runtime.

Este router expone `GET /photo-proxy?u=<sig_url>`: descarga la imagen del
SIG vía httpx y la reenvía al cliente con CORS abierto. Si se solicita
`size=thumb`, genera una miniatura local y la reutiliza en siguientes
peticiones. Solo acepta URLs bajo `https://sig.caceres.es/fotosOriginales/`
para que no se pueda abusar del backend como proxy genérico.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import tempfile
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.config import PHOTO_PROXY_CACHE_DIR, PHOTO_THUMBNAIL_MAX_SIZE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["photos"])


# Lista blanca: solo se reenvían imágenes que viven bajo el path de fotos
# originales del SIG. Cualquier otra URL se rechaza con 400 para evitar
# que el endpoint se use como proxy abierto.
_ALLOWED_HOST = "sig.caceres.es"
_ALLOWED_PATH_PREFIX = "/fotosOriginales/"

# El SIG redirige HTTP→HTTPS con 301; mantenemos `follow_redirects` y
# `verify=False` por la misma razón que en `photo_resolver`.
_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "AparCaceres-photoproxy/1.0"

# Cabeceras de respuesta que reenviamos del SIG al cliente, si están.
_FORWARD_RESPONSE_HEADERS: tuple[str, ...] = (
    "content-type",
    "content-length",
    "last-modified",
    "etag",
)

_THUMBNAIL_CONTENT_TYPE = "image/jpeg"
_THUMBNAIL_SUFFIX = ".jpg"


@router.get(
    "/photo-proxy",
    summary="Proxy CORS-friendly de imágenes del SIG municipal",
    description=(
        "Descarga la imagen indicada en `u` del SIG (`sig.caceres.es/"
        "fotosOriginales/...`) y la reenvía con `Access-Control-Allow-"
        "Origin: *` para que el cliente Flutter web pueda renderizarla. "
        "Con `size=thumb` genera una miniatura cacheada en disco. Solo "
        "acepta URLs bajo el path permitido; cualquier otra URL devuelve 400."
    ),
    responses={
        200: {"description": "La imagen, con cabeceras CORS abiertas."},
        400: {"description": "URL no permitida o mal formada."},
        502: {"description": "El SIG no respondió o devolvió un error."},
    },
)
async def photo_proxy(
    u: str = Query(..., description="URL completa de la imagen en sig.caceres.es"),
    size: Literal["original", "thumb"] = Query(
        "original",
        description="`thumb` devuelve una miniatura generada y cacheada localmente.",
    ),
) -> Response:
    target = _validate_target(u)
    if target is None:
        raise HTTPException(status_code=400, detail="URL no permitida")

    if size == "thumb":
        cached_thumb = _thumbnail_cache_path(target)
        if cached_thumb.exists():
            return _thumbnail_file_response(cached_thumb)

    upstream = await _fetch_upstream_image(target)

    if upstream.status_code != 200:
        return _empty_upstream_error(upstream.status_code)

    if size == "thumb":
        try:
            cached_thumb = await asyncio.to_thread(
                _write_thumbnail_cache,
                target,
                upstream.content,
            )
        except ValueError as exc:
            logger.warning("photo-proxy: imagen no convertible a miniatura %s (%s)", target, exc)
            return _original_image_response(upstream)

        return _thumbnail_file_response(cached_thumb)

    return _original_image_response(upstream)


async def _fetch_upstream_image(target: str) -> httpx.Response:
    headers = {"User-Agent": _USER_AGENT, "Accept": "image/*,*/*"}
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, verify=False, headers=headers
        ) as client:
            return await client.get(target, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.warning("photo-proxy: fallo al descargar %s (%s)", target, exc)
        raise HTTPException(status_code=502, detail="No se pudo obtener la imagen") from exc


def _empty_upstream_error(status_code: int) -> Response:
    # Pasamos el status del SIG al cliente, pero acotado a un rango razonable
    # para que un 5xx upstream no se confunda con un fallo nuestro en métricas.
    status = 502 if status_code >= 500 else status_code
    return Response(content=b"", status_code=status, headers=_cors_headers())


def _original_image_response(upstream: httpx.Response) -> Response:
    response_headers = _cors_headers()
    for key in _FORWARD_RESPONSE_HEADERS:
        value = upstream.headers.get(key)
        if value:
            response_headers[key] = value
    # Cache agresivo: las fotos del SIG no cambian. 7 días en CDN intermedio
    # y en el navegador del cliente reduce la presión sobre el backend.
    response_headers.setdefault("cache-control", "public, max-age=604800, immutable")

    return Response(content=upstream.content, headers=response_headers)


def _thumbnail_cache_path(target: str) -> Path:
    digest = hashlib.sha256(target.encode("utf-8")).hexdigest()
    return PHOTO_PROXY_CACHE_DIR / f"{digest}{_THUMBNAIL_SUFFIX}"


def _write_thumbnail_cache(target: str, image_bytes: bytes) -> Path:
    cache_path = _thumbnail_cache_path(target)
    if cache_path.exists():
        return cache_path

    PHOTO_PROXY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail(
                (PHOTO_THUMBNAIL_MAX_SIZE, PHOTO_THUMBNAIL_MAX_SIZE),
                Image.Resampling.LANCZOS,
            )
            image = _to_rgb(image)
            with tempfile.NamedTemporaryFile(
                delete=False,
                dir=PHOTO_PROXY_CACHE_DIR,
                suffix=".tmp",
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                image.save(tmp_file, format="JPEG", quality=82, optimize=True)
        if tmp_path is None:
            raise ValueError("miniatura no generada")
        tmp_path.replace(cache_path)
    except (OSError, UnidentifiedImageError) as exc:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise ValueError("imagen no soportada") from exc

    return cache_path


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image

    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.convert("RGBA").getchannel("A")
        background.paste(image.convert("RGBA"), mask=alpha)
        return background

    return image.convert("RGB")


def _thumbnail_file_response(path: Path) -> FileResponse:
    headers = _cors_headers()
    headers["cache-control"] = "public, max-age=604800, immutable"
    return FileResponse(path, media_type=_THUMBNAIL_CONTENT_TYPE, headers=headers)


def _validate_target(raw_url: str) -> Optional[str]:
    """Devuelve la URL si pasa el allowlist; `None` si la rechaza.

    Aceptamos solo `https://sig.caceres.es/fotosOriginales/...` (también
    `http://`, que el SIG redirige a HTTPS por su cuenta). Cualquier otro
    host o path se descarta.
    """
    if not raw_url:
        return None
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname != _ALLOWED_HOST:
        return None
    if not parsed.path.startswith(_ALLOWED_PATH_PREFIX):
        return None
    return raw_url


def _cors_headers() -> dict[str, str]:
    """Cabeceras CORS abiertas. Las imágenes son públicas, no hay credenciales."""
    return {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET",
        "cross-origin-resource-policy": "cross-origin",
    }
