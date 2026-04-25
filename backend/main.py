from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.redis_client import lifespan
from app.routers import favorites, health, imports, parkings

app = FastAPI(
    title="AparCaceres API",
    description="API para localización de aparcamientos públicos en Cáceres usando RedisDB",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: permite que el cliente (Flutter web, navegador, etc.) llame a la API desde
# otro origen. Con "*" y allow_credentials=False funciona para dev; en producción
# conviene restringir CORS_ORIGINS a la URL real del cliente.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Orden de inclusión de routers: no afecta a la resolución de rutas entre distintos
# prefijos, pero sí dentro de un mismo router (/parkings/nearby va antes que
# /parkings/{parking_id} dentro de parkings.py).
app.include_router(health.router)
app.include_router(imports.router)
app.include_router(parkings.router)
app.include_router(favorites.router)
