"""Resolución de URLs de foto para aparcamientos sin `URL_FOTO` explícita.

Solo dos datasets municipales (`movilidad_reducida` y `parking_bicis`) traen
una URL de imagen en el GeoJSON. Para el resto, la URL que llega es la de la
ficha HTML del SIG (`fichatoponimia.php?mslink=...` o `fichacalle.php?codigo=...`),
que embebe la foto del lugar en su `<img src="/fotosOriginales/.../...jpg">`.

Este módulo:
  - Define `extract_photo_url(html)` para parsear ese HTML con un regex
    deliberadamente acotado a la primera imagen que viva bajo
    `/fotosOriginales/`. Sin BeautifulSoup ni dependencias pesadas:
    solo un regex que es trivial de testear y no carga DOM completo.
  - Expone `resolve_photo_url(client, ficha_url)` que descarga la ficha y
    aplica el extractor.
  - Expone `resolve_many` para resolver una lista de pares (id, ficha_url)
    en paralelo con un semáforo, usando una caché Redis por `place_id`
    para que un reimport no rescraperar lo ya descubierto.

Convención de la caché:
  parking_photo:{id} → "https://..." (URL resuelta) o "" (no hay foto).
  TTL aplicado = `PHOTO_CACHE_TTL_SECONDS`. Las cuentas vacías cachean
  igualmente para no martillear fichas que jamás van a tener foto.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urljoin

import httpx
import redis

from .config import (
    PHOTO_CACHE_KEY_PREFIX,
    PHOTO_CACHE_TTL_SECONDS,
    PHOTO_FETCH_CONCURRENCY,
    PHOTO_FETCH_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


# Sentinel que persistimos cuando comprobamos que la ficha no tiene foto.
# Una cadena vacía es indistinguible en la API pública (la URL ausente cae a
# `imageUrl=None` igual), pero permite que el cache HIT distinga "ya miramos
# y no hay" de "todavía no lo intentamos".
_CACHE_NEGATIVE_SENTINEL = ""

# Regex deliberadamente conservador: busca un `<img>` cuyo `src` apunte a
# `/fotosOriginales/...` con una extensión de imagen. La barra inicial es la
# pista clave (todas las URLs del SIG empiezan así); evita confundir con
# imágenes de iconos en `../imagenes/`. Insensible a mayúsculas para tolerar
# `JPG` y `jpg`.
_PHOTO_RE = re.compile(
    r'<img\b[^>]*\bsrc\s*=\s*"(?P<url>/fotosOriginales/[^"]+\.(?:jpe?g|png|gif|webp))"',
    re.IGNORECASE,
)

# El SIG sirve sus fichas tras un 301 a HTTPS; ese es el host base que usamos
# para reconstruir URLs absolutas a partir del `src` relativo embebido.
_SIG_BASE = "https://sig.caceres.es"

# User-Agent identificable. No es un trick anti-bots: el SIG no parece tener
# rate-limit visible, pero conviene declararse honestamente.
_USER_AGENT = "AparCaceres-importer/1.0 (+https://github.com/cesarsm24/AparCaceres)"


def extract_photo_url(html: str, *, base_url: str = _SIG_BASE) -> Optional[str]:
    """Devuelve la URL absoluta de la primera foto del SIG embebida en `html`.

    Devuelve `None` si no encuentra ninguna `<img>` apuntando a
    `/fotosOriginales/...`. Función pura: misma entrada → misma salida,
    fácil de testear contra fixtures.
    """
    if not html:
        return None
    match = _PHOTO_RE.search(html)
    if match is None:
        return None
    relative = match.group("url")
    return urljoin(base_url, relative)


@dataclass(frozen=True)
class _ResolveTask:
    place_id: str
    ficha_url: str


async def _fetch_ficha(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Descarga el HTML de una ficha. Devuelve `None` ante cualquier fallo.

    Tratamos errores como "no hay foto" en silencio para que un import no se
    aborte por fichas inaccesibles. El log queda a nivel DEBUG porque a la
    escala del catálogo (miles de features) un WARNING por ficha rota
    inundaría los logs.
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


async def resolve_photo_url(
    client: httpx.AsyncClient,
    ficha_url: str,
) -> Optional[str]:
    """Descarga la ficha y extrae la primera URL de foto. None si no hay."""
    html = await _fetch_ficha(client, ficha_url)
    if html is None:
        return None
    return extract_photo_url(html, base_url=str(client.base_url) or _SIG_BASE)


async def resolve_many(
    tasks: Iterable[tuple[str, str]],
    rdb: redis.Redis,
    *,
    concurrency: int = PHOTO_FETCH_CONCURRENCY,
    timeout: float = PHOTO_FETCH_TIMEOUT_SECONDS,
    cache_ttl: int = PHOTO_CACHE_TTL_SECONDS,
) -> dict[str, str]:
    """Resuelve `(place_id, ficha_url)` en paralelo y devuelve `{id: imageUrl}`.

    Pasos:
      1. Lookup en `parking_photo:{id}`. Si hay HIT, lo devolvemos sin red.
         El sentinel `""` se respeta como HIT también (no rescraperar).
      2. MISS → encolar fetch dentro del semáforo. La concurrencia evita
         saturar al SIG; un import completo cabe en <1 minuto con 20 hilos.
      3. Persistir el resultado (positivo o negativo) en Redis con TTL.
      4. Solo devolvemos las entradas con URL no vacía. Los callers no
         necesitan saber del sentinel.
    """
    pending: list[_ResolveTask] = []
    resolved: dict[str, str] = {}

    for place_id, ficha_url in tasks:
        if not place_id or not ficha_url:
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
        pending.append(_ResolveTask(place_id=place_id, ficha_url=ficha_url))

    if not pending:
        return resolved

    semaphore = asyncio.Semaphore(concurrency)
    timeout_obj = httpx.Timeout(timeout)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}

    # `verify=False`: el SIG sirve su cert por FNMT-RCM (CA del gobierno
    # español), que no está incluida en el bundle por defecto de `certifi`.
    # Con verificación activa el redirect 301 → HTTPS truena con
    # `CERTIFICATE_VERIFY_FAILED` y todas las fichas caen al sentinel
    # negativo. Estamos haciendo GET de páginas públicas sin credenciales:
    # un MITM como mucho podría devolvernos URLs de imagen falsas, que el
    # cliente móvil renderizaría con un 404 inocuo. El trade-off vale la
    # pena para no depender del bundle de CA del runtime.
    async with httpx.AsyncClient(
        timeout=timeout_obj,
        headers=headers,
        base_url=_SIG_BASE,
        verify=False,
    ) as client:
        async def _worker(task: _ResolveTask) -> tuple[str, Optional[str]]:
            async with semaphore:
                url = await resolve_photo_url(client, task.ficha_url)
                return task.place_id, url

        results = await asyncio.gather(
            *[_worker(t) for t in pending],
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
            # Si Redis cae a mitad de pipeline, salimos: no es crítico para el
            # import, las próximas vueltas reintentarán cachear.
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
