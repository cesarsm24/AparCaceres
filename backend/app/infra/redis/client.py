"""Clientes Redis compartidos del servicio.

Esta capa centraliza la conexión a Redis Stack para todo el backend. Expone
un cliente asíncrono para handlers HTTP y un cliente síncrono para flujos
pesados ejecutados fuera del event loop, como la importación del catálogo y
la construcción de consultas RediSearch.

El `lifespan` crea ambos clientes al arrancar, intenta verificar la
disponibilidad del servidor y prepara el índice de búsqueda si RediSearch
responde. La ausencia inicial de Redis no aborta el arranque: los handlers
devuelven 503 cuando necesitan el cliente y la dependencia no está operativa.
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
    """Construye el pool Redis asíncrono usado por los handlers HTTP.

    El pool comparte parámetros con el cliente síncrono para mantener el
    mismo contrato de conectividad frente al mismo servidor Redis.
    """
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
    """Construye el cliente Redis síncrono usado por flujos en thread.

    Se usa con `asyncio.to_thread` para operaciones bloqueantes que no se
    benefician de una API asíncrona propia.
    """
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

    El arranque valida la conectividad, registra el estado del backend y
    garantiza el índice principal de RediSearch cuando el módulo está
    disponible. Si Redis todavía no responde, la aplicación sigue en pie y
    las rutas devolverán 503 al intentar acceder a la dependencia.
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
    """Devuelve el cliente Redis asíncrono de la aplicación.

    Lo usan los handlers que realizan operaciones directas y cortas sobre
    Redis sin necesidad de saltar a un hilo adicional.
    """
    return request.app.state.redis


def get_redis_sync(request: Request) -> redis.Redis:
    """Devuelve el cliente Redis síncrono de la aplicación.

    Lo usan los handlers que delegan en `asyncio.to_thread` para mantener el
    event loop libre mientras se ejecutan consultas o importaciones pesadas.
    """
    return request.app.state.redis_sync


def raise_redis_503(exc: Exception) -> HTTPException:
    """Convierte un fallo de Redis en una respuesta HTTP 503.

    Mantiene homogéneo el contrato de error cuando la infraestructura de
    persistencia o búsqueda no está disponible.
    """
    return HTTPException(status_code=503, detail=f"Redis no disponible: {exc}")
