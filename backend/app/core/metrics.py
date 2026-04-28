"""Instrumentación Prometheus del servicio FastAPI.

Configura `prometheus-fastapi-instrumentator` para exponer métricas HTTP en
`/metrics` sin instrumentar manualmente cada router. La instrumentación puede
desactivarse mediante `METRICS_ENABLED=false`, especialmente en tests para
evitar estado global compartido del cliente Prometheus.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def _env_flag(name: str, default: bool) -> bool:
    """Interpreta una variable de entorno como valor booleano."""
    raw = os.getenv(name)
    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


METRICS_ENABLED = _env_flag("METRICS_ENABLED", True)


def instrument_app(app: FastAPI) -> None:
    """Registra métricas Prometheus y expone el endpoint `/metrics`.

    Los códigos de estado se conservan sin agrupar para facilitar diagnósticos
    por respuesta exacta. `/metrics` y `/healthz` se excluyen para evitar que
    los scrapes y comprobaciones de salud contaminen las métricas de negocio.
    """
    if not METRICS_ENABLED:
        return

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/healthz"],
        env_var_name="METRICS_ENABLED",
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)