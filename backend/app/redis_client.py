import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, Request

from .config import REDIS_DB, REDIS_HOST, REDIS_PORT

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Abre la conexión a Redis al arrancar la app y la cierra al apagarla.

    Usamos el patrón `lifespan` (sustituye a on_event) para que el cliente viva
    durante toda la vida del proceso y se reutilice entre requests.
    """
    # decode_responses=True -> Redis devuelve strings en lugar de bytes.
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )
    try:
        # PING: comprobación rápida de que el servidor responde. Si falla, solo logueamos;
        # los endpoints devolverán 503 cuando intenten usarlo.
        client.ping()
        logger.info("Conexión a Redis establecida en %s:%s (db=%s)", REDIS_HOST, REDIS_PORT, REDIS_DB)
    except redis.ConnectionError as exc:
        logger.warning("No se pudo conectar a Redis al arrancar: %s", exc)

    app.state.redis = client
    yield
    client.close()


def get_redis(request: Request) -> redis.Redis:
    """Dependency de FastAPI: expone el cliente de Redis guardado en app.state."""
    return request.app.state.redis


def raise_redis_503(exc: Exception) -> HTTPException:
    """Helper: convierte un fallo de conexión a Redis en HTTP 503."""
    return HTTPException(status_code=503, detail=f"Redis no disponible: {exc}")
