"""Configuración de logging estructurado en JSON.

Sin dependencias externas: extiende `logging.Formatter` para serializar cada
registro como una línea JSON, lista para que un colector tipo Loki / ELK /
Cloud Logging la indexe sin parseo adicional.

Cada línea incluye al menos `timestamp`, `level`, `logger`, `message` y, cuando
se encuentra disponible en el contexto, `request_id` (lo inyecta el middleware
`RequestIdMiddleware` mediante un `ContextVar`).

El nivel raíz se controla con la variable de entorno `LOG_LEVEL` (default
`INFO`). En desarrollo conviene `DEBUG`; en producción `INFO` o `WARNING`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Cabecera HTTP estándar para correlación (lo emite el cliente o el proxy).
REQUEST_ID_HEADER = "X-Request-ID"

# `ContextVar` por request: el formatter lo lee de aquí en lugar de pedírselo
# explícitamente al logger en cada llamada.
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


# Atributos estándar del LogRecord que ya cubrimos en los campos top-level.
# El resto se vuelca a `extra` para no perderse.
_RESERVED_RECORD_ATTRS: frozenset[str] = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class JsonFormatter(logging.Formatter):
    """Formatter mínimo que emite una línea JSON por registro."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_ctx.get(),
        }

        # Cualquier `extra={...}` que el código haya pasado a `logger.x(...)`
        # acaba como atributo del record. Lo serializamos para no perderlo.
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue
            payload.setdefault(key, _safe_json(value))

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=_safe_json)


def _safe_json(value: Any) -> Any:
    """Convierte tipos no serializables a su `repr` para no romper el dump."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def configure_logging(level: str | None = None) -> None:
    """Instala el `JsonFormatter` en el handler raíz de stderr.

    Idempotente: si ya hay handlers configurados, los sustituye para garantizar
    el formato JSON en cualquier entorno (uvicorn, pytest, scripts ad-hoc).
    """
    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved_level)

    # Uvicorn instala sus propios loggers (`uvicorn`, `uvicorn.access`,
    # `uvicorn.error`). Los enchufamos al mismo handler para tener una única
    # corriente de logs JSON.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(noisy)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
        uvicorn_logger.setLevel(resolved_level)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Asigna un `request_id` por request y lo refleja en la respuesta.

    Si el cliente envía `X-Request-ID`, se respeta (útil para correlacionar
    entre el front, el proxy y el backend). Si no, se genera un UUID4 corto.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming.strip() if incoming and incoming.strip() else uuid.uuid4().hex
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
