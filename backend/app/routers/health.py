"""Endpoints de salud del servicio.

`GET /` mantiene el saludo simple por compatibilidad con cualquier
comprobación ligera previa. `GET /healthz` es el healthcheck real para
loadbalancers, Kubernetes y docker-compose: comprueba el `PING` async a
Redis y la disponibilidad del índice RediSearch (`FT.INFO`).

Códigos:
- 200 cuando todas las dependencias responden.
- 503 cuando alguna dependencia crítica está caída. La respuesta incluye el
  desglose por componente para que el operador identifique el origen.
"""

from __future__ import annotations

import logging
from typing import Optional

import redis
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response
from redis.exceptions import ResponseError

from ..config import SEARCH_INDEX_NAME
from ..redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/")
def read_root():
    """Saludo plano. Útil como liveness check muy ligero."""
    return {"status": "Backend configurado y listo"}


@router.get(
    "/healthz",
    summary="Healthcheck con dependencias",
    description=(
        "Comprueba `PING` a Redis y `FT.INFO` sobre el índice RediSearch. "
        "Devuelve 200 cuando todo responde y 503 cuando alguna dependencia "
        "crítica falla, con desglose por componente para depuración."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "redis": {"status": "ok"},
                        "search_index": {
                            "status": "ok",
                            "name": SEARCH_INDEX_NAME,
                            "num_docs": 7314,
                        },
                    }
                }
            }
        },
        503: {
            "description": "Alguna dependencia crítica no responde.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "degraded",
                        "redis": {"status": "down", "error": "Connection refused"},
                        "search_index": {"status": "unknown"},
                    }
                }
            },
        },
    },
)
async def healthz(
    response: Response,
    rdb: aioredis.Redis = Depends(get_redis),
):
    redis_status = await _check_redis(rdb)
    search_status = (
        await _check_search_index(rdb)
        if redis_status["status"] == "ok"
        else {"status": "unknown"}
    )

    overall_ok = (
        redis_status["status"] == "ok"
        and search_status["status"] == "ok"
    )
    if not overall_ok:
        response.status_code = 503

    return {
        "status": "ok" if overall_ok else "degraded",
        "redis": redis_status,
        "search_index": search_status,
    }


async def _check_redis(rdb) -> dict:
    try:
        await rdb.ping()
    except (redis.ConnectionError, redis.TimeoutError, OSError) as exc:
        logger.warning("Healthcheck: Redis no responde (%s)", exc)
        return {"status": "down", "error": str(exc)}
    return {"status": "ok"}


async def _check_search_index(rdb) -> dict:
    if not hasattr(rdb, "execute_command"):
        # Cliente sin soporte para comandos arbitrarios (p. ej. AsyncFakeRedis
        # en tests). Se trata como "ok" con num_docs desconocido.
        return {"status": "ok", "name": SEARCH_INDEX_NAME, "num_docs": None}
    try:
        info = await rdb.execute_command("FT.INFO", SEARCH_INDEX_NAME)
    except ResponseError as exc:
        msg = str(exc).lower()
        if "unknown index" in msg or "no such index" in msg:
            return {"status": "missing", "name": SEARCH_INDEX_NAME, "error": str(exc)}
        if "unknown command" in msg or "module" in msg:
            return {"status": "down", "error": "RediSearch no disponible"}
        logger.warning("Healthcheck: FT.INFO devolvió error inesperado (%s)", exc)
        return {"status": "down", "error": str(exc)}
    except (redis.ConnectionError, redis.TimeoutError, OSError) as exc:
        return {"status": "down", "error": str(exc)}

    return {
        "status": "ok",
        "name": SEARCH_INDEX_NAME,
        "num_docs": _extract_num_docs(info),
    }


def _extract_num_docs(info) -> Optional[int]:
    """`FT.INFO` devuelve una lista plana `[k, v, k, v, ...]`. Extrae `num_docs`."""
    if isinstance(info, dict):
        value = info.get("num_docs")
        return int(value) if value is not None else None
    if not isinstance(info, (list, tuple)):
        return None
    for i in range(0, len(info) - 1, 2):
        if str(info[i]) == "num_docs":
            try:
                return int(info[i + 1])
            except (TypeError, ValueError):
                return None
    return None
