"""Instrumentación Prometheus para el servicio FastAPI.

Usa `prometheus-fastapi-instrumentator` para exponer en `/metrics` las
métricas estándar (histograma de latencia, contador de status codes,
inflight requests, etc.) sin tener que instrumentar manualmente cada router.

`/metrics` queda fuera de los logs de acceso para no inundar el JSON con
scrapes de Prometheus (un scrape cada 15s × 8640 al día). Por la misma
razón también se excluye `/healthz`.

Desactivable con `METRICS_ENABLED=false` (útil en tests para no arrastrar el
estado global del cliente Prometheus entre casos).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


METRICS_ENABLED = _env_flag("METRICS_ENABLED", True)


def instrument_app(app: FastAPI) -> None:
    """Engancha la instrumentación al ciclo de vida de la app.

    `should_group_status_codes=False` mantiene los códigos exactos (200, 404,
    503...) en vez de agruparlos por familia (`2xx`/`5xx`). Más útil para
    dashboards al precio de un poco más de cardinalidad — aceptable con la
    docena de rutas del servicio.
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
    # `expose` registra el endpoint `/metrics` en el arranque.
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
