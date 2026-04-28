"""Entrypoint del servicio FastAPI.

Construye la aplicación, configura middleware transversal, registra métricas,
rate limiting y routers. El logging se inicializa antes de crear la app para
que los mensajes del ciclo de vida salgan en formato estructurado.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import CORS_ALLOW_ALL, CORS_ORIGINS, LOG_LEVEL
from app.core.logging import RequestIdMiddleware, configure_logging
from app.core.metrics import instrument_app
from app.core.rate_limit import limiter
from app.infra.redis.client import lifespan
from app.routers import auth, favorites, health, imports, parkings, photos

configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="AparCaceres API",
    description="API para localización de aparcamientos públicos en Cáceres usando Redis Stack",
    version="0.2.0",
    lifespan=lifespan,
)

if CORS_ORIGINS:
    if CORS_ALLOW_ALL:
        logger.warning(
            "CORS configurado con '*'. Este valor solo debe usarse en desarrollo."
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
        "CORS deshabilitado por ausencia de orígenes permitidos."
    )

# Starlette ejecuta los middlewares en orden inverso al registro. Este
# middleware debe ser el más externo para que también cubra respuestas CORS
# generadas antes de entrar en los routers.
app.add_middleware(RequestIdMiddleware)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

instrument_app(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(imports.router)
app.include_router(parkings.router)
app.include_router(favorites.router)
app.include_router(photos.router)