"""Resolución de fotos embebidas en fichas municipales.

Esta capa extrae URLs de imagen desde fichas HTML del SIG municipal para los
aparcamientos que no incluyen `URL_FOTO` en el GeoJSON. El resultado se cachea
en Redis por id de aparcamiento, incluyendo resultados negativos, para evitar
scraping repetido en importaciones sucesivas y mantener estable el coste del
importador.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence
from urllib.parse import urljoin

import httpx
import redis

from ...core.config import (
    PHOTO_CACHE_KEY_PREFIX,
    PHOTO_CACHE_TTL_SECONDS,
    PHOTO_FETCH_CONCURRENCY,
    PHOTO_FETCH_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


_CACHE_NEGATIVE_SENTINEL = ""

_PHOTO_ATTR_RE = re.compile(
    r'\b(?:src|href)\s*=\s*(?P<q>["\'])(?P<url>[^"\']*fotosOriginales[^"\']*\.(?:jpe?g|png|gif|webp)[^"\']*)(?P=q)',
    re.IGNORECASE,
)

_SIG_BASE = "https://sig.caceres.es"
_USER_AGENT = "AparCaceres-importer/1.0 (+https://github.com/cesarsm24/AparCaceres)"


def extract_photo_url(html: str, *, base_url: str = _SIG_BASE) -> Optional[str]:
    """Extrae la primera URL de foto válida encontrada en una ficha HTML.

    La búsqueda prioriza atributos `src` y `href` que apunten a recursos de
    `fotosOriginales`, porque son las rutas que publica el SIG para imágenes de
    aparcamiento.
    """
    if not html:
        return None

    for match in _PHOTO_ATTR_RE.finditer(html):
        candidate = _normalize_sig_photo_url(match.group("url"), base_url=base_url)
        if candidate is not None:
            return candidate

    return None


def _normalize_sig_photo_url(raw_url: str, *, base_url: str = _SIG_BASE) -> Optional[str]:
    """Normaliza variantes de URL del SIG y valida que apunten a una imagen.

    Corrige variantes relativas, escapes de HTML y formas degeneradas del
    esquema antes de aceptar la URL como imagen pública del SIG.
    """
    if not raw_url:
        return None

    candidate = html_lib.unescape(raw_url).strip()
    candidate = candidate.replace("\\", "/")
    candidate = re.sub(r"^https:/+", "https://", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^http:/+", "http://", candidate, flags=re.IGNORECASE)

    if candidate.startswith("//"):
        candidate = "https:" + candidate

    if candidate.startswith("/fotosOriginales/"):
        candidate = urljoin(base_url, candidate)

    if not _looks_like_image_url(candidate):
        return None

    return candidate


@dataclass(frozen=True)
class _ResolveTask:
    """Unidad de resolución de foto para un aparcamiento."""

    place_id: str
    candidate_urls: tuple[str, ...]


async def _fetch_ficha(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Descarga una ficha HTML sin propagar errores de red al importador.

    La función convierte fallos de red o respuestas no exitosas en `None` para
    que la resolución de fotos no interrumpa la importación del catálogo.
    """
    try:
        response = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.debug("Ficha %s inaccesible: %s", url, exc)
        return None

    if response.status_code != 200:
        logger.debug("Ficha %s devolvió %s", url, response.status_code)
        return None

    return response.text


def _looks_like_image_url(url: str) -> bool:
    """Comprueba si una URL apunta a una imagen publicada por el SIG.

    Se aplica una validación conservadora para evitar cachear enlaces que no
    correspondan a imágenes servidas por el dominio municipal.
    """
    lower = url.lower()
    return lower.startswith(("http://", "https://")) and "/fotosoriginales/" in lower and (
        lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
    )


async def resolve_photo_url(
    client: httpx.AsyncClient,
    ficha_url: str,
) -> Optional[str]:
    """Resuelve la primera foto embebida en una ficha municipal.

    Obtiene la ficha, extrae la primera URL válida y devuelve `None` si la
    página no está disponible o no contiene una imagen utilizable.
    """
    html = await _fetch_ficha(client, ficha_url)
    if html is None:
        return None

    return extract_photo_url(html, base_url=str(client.base_url) or _SIG_BASE)


async def resolve_photo_url_from_candidates(
    client: httpx.AsyncClient,
    candidate_urls: Sequence[str],
) -> Optional[str]:
    """Devuelve la primera imagen válida entre varias URLs candidatas.

    Permite mezclar URLs ya resueltas con fichas HTML. Si una candidata ya es
    una imagen válida, se devuelve sin realizar otra petición HTTP.
    """
    for candidate in candidate_urls:
        if not candidate:
            continue

        if _looks_like_image_url(candidate):
            return candidate

        photo = await resolve_photo_url(client, candidate)
        if photo:
            return photo

    return None


async def resolve_many(
    tasks: Iterable[tuple[str, str | Sequence[str]]],
    rdb: redis.Redis,
    *,
    concurrency: int = PHOTO_FETCH_CONCURRENCY,
    timeout: float = PHOTO_FETCH_TIMEOUT_SECONDS,
    cache_ttl: int = PHOTO_CACHE_TTL_SECONDS,
) -> dict[str, str]:
    """Resuelve fotos en paralelo y devuelve solo resultados positivos.

    La caché distingue entre ausencia de entrada y resultado negativo ya
    comprobado mediante un sentinel vacío persistido en Redis. Así se evita
    repetir peticiones a fichas que ya se sabe que no contienen imagen.
    """
    pending: list[_ResolveTask] = []
    resolved: dict[str, str] = {}

    for place_id, raw_candidates in tasks:
        if not place_id or not raw_candidates:
            continue

        if isinstance(raw_candidates, str):
            candidate_urls = (raw_candidates,)
        else:
            candidate_urls = tuple(
                candidate for candidate in raw_candidates if candidate
            )

        if not candidate_urls:
            continue

        cache_key = f"{PHOTO_CACHE_KEY_PREFIX}{place_id}"

        try:
            cached = rdb.get(cache_key)
        except redis.ConnectionError:
            cached = None

        if cached is not None:
            decoded = cached.decode("utf-8") if isinstance(cached, bytes) else cached
            if decoded:
                resolved[place_id] = decoded
            continue

        pending.append(
            _ResolveTask(place_id=place_id, candidate_urls=candidate_urls)
        )

    if not pending:
        return resolved

    semaphore = asyncio.Semaphore(concurrency)
    timeout_obj = httpx.Timeout(timeout)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}

    # El SIG puede presentar certificados no incluidos en el bundle del runtime.
    # Solo se hacen lecturas públicas sin credenciales, por lo que se prioriza
    # la disponibilidad del import sobre la verificación estricta de TLS.
    async with httpx.AsyncClient(
        timeout=timeout_obj,
        headers=headers,
        base_url=_SIG_BASE,
        verify=False,
    ) as client:

        async def _worker(task: _ResolveTask) -> tuple[str, Optional[str]]:
            async with semaphore:
                url = await resolve_photo_url_from_candidates(
                    client,
                    task.candidate_urls,
                )
                return task.place_id, url

        results = await asyncio.gather(
            *[_worker(task) for task in pending],
            return_exceptions=False,
        )

    pipe = rdb.pipeline()
    pipe_used = False

    for place_id, url in results:
        cache_key = f"{PHOTO_CACHE_KEY_PREFIX}{place_id}"
        value = url if url else _CACHE_NEGATIVE_SENTINEL

        try:
            pipe.set(cache_key, value, ex=cache_ttl if cache_ttl > 0 else None)
            pipe_used = True
        except redis.ConnectionError:
            logger.warning("Redis no disponible al cachear fotos resueltas")
            break

        if url:
            resolved[place_id] = url

    if pipe_used:
        try:
            pipe.execute()
        except redis.ConnectionError:
            logger.warning("Pipeline de caché de fotos falló al ejecutar")

    return resolved
