"""Entrypoint del servicio FastAPI.

Orquesta:
  1. Configuración de logging estructurado (debe ejecutarse antes de instanciar
     la app para que los logs del lifespan ya salgan en formato JSON).
  2. Creación de la app + lifespan (cliente Redis compartido).
  3. Middleware: `RequestIdMiddleware` antes que `CORSMiddleware` para que los
     preflight OPTIONS también reciban un `X-Request-ID` correlacionable.
  4. Inclusión de routers.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ALLOW_ALL, CORS_ORIGINS, LOG_LEVEL
from app.logging_config import RequestIdMiddleware, configure_logging
from app.redis_client import lifespan
from app.routers import favorites, health, imports, parkings

configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="AparCaceres API",
    description="API para localización de aparcamientos públicos en Cáceres usando Redis Stack",
    version="0.1.0",
    lifespan=lifespan,
)


# `RequestIdMiddleware` se monta primero para que aparezca al final de la
# cadena (FastAPI ejecuta los middlewares en orden inverso al de inserción).
# Así el request id se asigna antes que cualquier otro middleware lo necesite.
app.add_middleware(RequestIdMiddleware)


# CORS: solo se monta si hay orígenes declarados. Sin orígenes, no se añade
# la cabecera y los navegadores rechazarán las peticiones cross-origin (lo
# correcto cuando solo sirve a clientes nativos sin Origin). Si alguien pone
# "*" en producción, se loggea como warning para que sea visible en métricas.
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


# Orden de inclusión de routers: no afecta a la resolución de rutas entre
# distintos prefijos, pero sí dentro de un mismo router (`/parkings/nearby`
# va antes que `/parkings/{parking_id}` dentro de `parkings.py`).
app.include_router(health.router)
app.include_router(imports.router)
app.include_router(parkings.router)
app.include_router(favorites.router)
