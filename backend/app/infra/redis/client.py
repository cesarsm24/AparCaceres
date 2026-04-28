"""Clientes Redis compartidos del servicio.

Proporciona un cliente asíncrono para handlers FastAPI y un cliente síncrono
para operaciones pesadas ejecutadas fuera del event loop. Ambos clientes usan
la misma configuración de conexión y se registran en el estado de la aplicación
durante el ciclo de vida.

El arranque no falla si Redis aún no está disponible; los endpoints devolverán
503 cuando intenten usar el cliente.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request

from ...core.config import REDIS_DB, REDIS_HOST, REDIS_PORT
from .search import SearchIndexError, ensure_search_index

logger = logging.getLogger(__name__)


def _build_async_pool() -> aioredis.ConnectionPool:
    """Construye el pool Redis asíncrono usado por los handlers."""
    return aioredis.ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        max_connections=50,
        health_check_interval=30,
        socket_keepalive=True,
        socket_timeout=5,
        socket_connect_timeout=2,
        retry_on_timeout=True,
    )


def _build_sync_client() -> redis.Redis:
    """Construye el cliente Redis síncrono usado por flujos en thread."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_keepalive=True,
        socket_timeout=5,
        socket_connect_timeout=2,
        health_check_interval=30,
        retry_on_timeout=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Registra clientes Redis durante el ciclo de vida de la aplicación.

    La disponibilidad inicial se comprueba para registrar el estado y crear el
    índice de búsqueda si RediSearch está operativo. La falta de conexión no
    impide arrancar el servicio.
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
    """Devuelve el cliente Redis asíncrono de la aplicación."""
    return request.app.state.redis


def get_redis_sync(request: Request) -> redis.Redis:
    """Devuelve el cliente Redis síncrono de la aplicación."""
    return request.app.state.redis_sync


def raise_redis_503(exc: Exception) -> HTTPException:
    """Convierte un fallo de Redis en una respuesta HTTP 503."""
    return HTTPException(status_code=503, detail=f"Redis no disponible: {exc}")