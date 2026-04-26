"""Entrypoint del servicio FastAPI.

Orquesta:
  1. Configuración de logging estructurado (debe ejecutarse antes de instanciar
     la app para que los logs del lifespan ya salgan en formato JSON).
  2. Creación de la app + lifespan (cliente Redis compartido, pool async).
  3. Middleware. Starlette ejecuta los middlewares en orden inverso al de
     `add_middleware`: el último registrado es el outermost. Por eso CORS se
     monta primero y `RequestIdMiddleware` después: así el request id se
     asigna antes que CORS responda los preflight `OPTIONS` y la cabecera
     `X-Request-ID` viaja también en esas respuestas.
  4. Instrumentación Prometheus (`/metrics`) y rate limiting global.
  5. Inclusión de routers.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import CORS_ALLOW_ALL, CORS_ORIGINS, LOG_LEVEL
from app.logging_config import RequestIdMiddleware, configure_logging
from app.metrics import instrument_app
from app.rate_limit import limiter
from app.redis_client import lifespan
from app.routers import auth, favorites, health, imports, parkings

configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="AparCaceres API",
    description="API para localización de aparcamientos públicos en Cáceres usando Redis Stack",
    version="0.2.0",
    lifespan=lifespan,
)


# CORS primero (acaba siendo el inner middleware). Solo se monta si hay
# orígenes declarados; en su ausencia los navegadores rechazarán las
# peticiones cross-origin (correcto cuando solo sirven clientes nativos sin
# `Origin`). Si alguien pone `*` en producción se loggea como warning para que
# sea visible en métricas.
if CORS_ORIGINS:
    if CORS_ALLOW_ALL:
        logger.warning(
            "CORS configurado con '*'. Aceptable solo en desarrollo; en "
            "producción declarar la lista explícita en CORS_ORIGINS."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-Cache",
            "X-Total-Count",
            "X-Truncated",
            "X-Limit",
            "X-Offset",
            "X-Request-ID",
        ],
    )
else:
    logger.info(
        "CORS deshabilitado (CORS_ORIGINS vacío). Solo aceptará peticiones "
        "sin cabecera Origin (clientes nativos)."
    )


# `RequestIdMiddleware` se registra al final para que sea el outermost: así
# corre antes que CORS y la respuesta a preflights `OPTIONS` también lleva el
# `X-Request-ID` correlacionable.
app.add_middleware(RequestIdMiddleware)


# Rate limiting global (slowapi). El limiter se inyecta en `app.state` para
# que las rutas decoradas con `@limiter.limit(...)` lo encuentren.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Métricas Prometheus en `/metrics` (latencia, status codes, etc.).
instrument_app(app)


# Orden de inclusión de routers: no afecta a la resolución de rutas entre
# distintos prefijos, pero sí dentro de un mismo router (`/parkings/nearby`
# va antes que `/parkings/{parking_id}` dentro de `parkings.py`).
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(imports.router)
app.include_router(parkings.router)
app.include_router(favorites.router)
