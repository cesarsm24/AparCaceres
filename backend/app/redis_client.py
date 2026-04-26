"""Clientes Redis del servicio: async para handlers, síncrono para flujos pesados.

El cliente async, con un `ConnectionPool` propio, sirve a los handlers que
solo necesitan comandos directos (hgetall, zadd, get, setex...): no bloquean
el event loop y aprovechan el pool entre requests.

Para los flujos pesados (importer multi-fichero y las consultas de
RediSearch encapsuladas en `app/search.py`) usamos un cliente síncrono: los
handlers async lo invocan vía `asyncio.to_thread`, así no arrastramos la
conversión async de la lógica de parsing y construcción de queries, que no
se beneficiaría del cambio.

Ambos clientes apuntan al mismo Redis y comparten parámetros (host/port/db).

`get_redis` y `get_redis_sync` son las dependencias FastAPI que los routers
importan. Mantener los nombres distintos evita confusiones (`rdb` síncrono
en search.py, `rdb` async en favorites/health).

Configuración del pool async:
- `max_connections=50`: holgado para una sola réplica; si se escala a varios
  workers, conviene revisarlo.
- `health_check_interval=30`: ping silencioso cada 30 s; mata conexiones
  rotas tras NAT timeouts antes de que un usuario las cobre como 503.
- `socket_keepalive=True`: TCP keepalive para detectar peers idos sin
  esperar al timeout del SO.
- `retry_on_timeout=True`: reintenta los comandos que fallen por
  `TimeoutError` (no por `ConnectionError`). Suficiente para flips de red.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request

from .config import REDIS_DB, REDIS_HOST, REDIS_PORT
from .search import SearchIndexError, ensure_search_index

logger = logging.getLogger(__name__)


def _build_async_pool() -> aioredis.ConnectionPool:
    return aioredis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        max_connections=50,
        health_check_interval=30,
        socket_keepalive=True,
        retry_on_timeout=True,
    )


def _build_sync_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_keepalive=True,
        health_check_interval=30,
        retry_on_timeout=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Abre los clientes Redis al arrancar y los cierra al apagarse.

    Si el `PING` falla, solo se loggea: los endpoints devolverán 503 cuando
    intenten usar el cliente. Eso permite que la app arranque incluso con
    Redis aún no disponible (por ejemplo en docker-compose, durante la
    ventana en que `redis` aún no responde a `healthcheck`).
    """
    pool = _build_async_pool()
    client = aioredis.Redis(connection_pool=pool)
    sync_client = _build_sync_client()
    try:
        await client.ping()
        logger.info(
            "Conexión a Redis establecida en %s:%s (db=%s)",
            REDIS_HOST,
            REDIS_PORT,
            REDIS_DB,
        )
        try:
            ensure_search_index(sync_client)
        except SearchIndexError as exc:
            logger.warning("Redis Stack / RediSearch no disponible: %s", exc)
    except (redis.ConnectionError, redis.exceptions.RedisError) as exc:
        logger.warning("No se pudo conectar a Redis al arrancar: %s", exc)

    app.state.redis = client
    app.state.redis_sync = sync_client
    try:
        yield
    finally:
        try:
            await client.aclose()
        finally:
            try:
                await pool.aclose()
            finally:
                sync_client.close()


def get_redis(request: Request) -> aioredis.Redis:
    """Dependency: cliente async para uso directo desde handlers async."""
    return request.app.state.redis


def get_redis_sync(request: Request) -> redis.Redis:
    """Dependency: cliente síncrono para `asyncio.to_thread(search_*, ...)`."""
    return request.app.state.redis_sync


def raise_redis_503(exc: Exception) -> HTTPException:
    """Helper: convierte un fallo de conexión a Redis en HTTP 503."""
    return HTTPException(status_code=503, detail=f"Redis no disponible: {exc}")
