"""Endpoint de emisión de tokens de sesión.

`POST /auth/session` recibe `{"sub": "<id-cliente>"}` y devuelve un JWT que
el cliente debe guardar y enviar como `Authorization: Bearer <token>` (o
`X-Session-Token`) en las llamadas a favoritos.

En esta fase la emisión confía en lo que envía el cliente: el modelo es
equivalente al `X-User-Id` opaco previo, pero ahora el cliente NO PUEDE
forjar la identidad de otro usuario sin la clave secreta. Cuando se integre
una capa de identidad real (OAuth/OIDC) este endpoint exigirá un assertion
externo previo.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..auth import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class SessionRequest(BaseModel):
    sub: str = Field(
        ...,
        max_length=128,
        description="Identificador opaco del cliente (device id, email, etc.).",
    )


class SessionResponse(BaseModel):
    token: str = Field(..., description="JWT a usar en `Authorization: Bearer`.")
    sub: str
    expiresAt: str = Field(..., description="ISO 8601 UTC de expiración.")
    tokenType: str = Field(default="Bearer")


_SESSION_RESPONSE_EXAMPLE = {
    "token": "eyJhbGciOi...",
    "sub": "device-abc-123",
    "expiresAt": "2026-05-26T10:00:00+00:00",
    "tokenType": "Bearer",
}


@router.post(
    "/session",
    response_model=SessionResponse,
    summary="Emite un token de sesión firmado para el sub indicado",
    description=(
        "Devuelve un JWT firmado con HS256 que el cliente envía en "
        "`Authorization: Bearer <token>` (o `X-Session-Token`) para acceder a "
        "los endpoints de favoritos. TTL por defecto: 30 días."
    ),
    responses={
        200: {"content": {"application/json": {"example": _SESSION_RESPONSE_EXAMPLE}}},
        400: {"description": "`sub` vacío o con caracteres inválidos."},
        503: {"description": "Auth no configurada (falta `FAVORITES_SECRET`)."},
    },
)
def create_session(payload: SessionRequest) -> SessionResponse:
    token, expires = issue_token(payload.sub)
    return SessionResponse(
        token=token,
        sub=payload.sub.strip(),
        expiresAt=expires.isoformat(),
    )
