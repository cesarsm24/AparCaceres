"""Endpoint para emitir tokens de sesión firmados.

Expone `POST /auth/session`, que recibe un identificador opaco de cliente y
devuelve un JWT utilizado por los endpoints protegidos. La emisión asume que
la identidad recibida ya es válida; la verificación externa queda delegada a
una futura capa de identidad.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..core.auth import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class SessionRequest(BaseModel):
    """Datos necesarios para emitir una sesión."""

    sub: str = Field(
        ...,
        max_length=128,
        description="Identificador opaco del cliente.",
    )


class SessionResponse(BaseModel):
    """Respuesta pública de emisión de sesión."""

    token: str = Field(..., description="JWT usado como token Bearer.")
    sub: str
    expiresAt: str = Field(..., description="Fecha de expiración en ISO 8601 UTC.")
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
    summary="Emite un token de sesión firmado",
    description=(
        "Devuelve un JWT firmado para acceder a los endpoints protegidos. "
        "El token debe enviarse en `Authorization: Bearer <token>` o "
        "`X-Session-Token`."
    ),
    responses={
        200: {"content": {"application/json": {"example": _SESSION_RESPONSE_EXAMPLE}}},
        400: {"description": "`sub` vacío o con caracteres inválidos."},
        503: {"description": "Autenticación no configurada."},
    },
)
def create_session(payload: SessionRequest) -> SessionResponse:
    """Emite una sesión para el identificador recibido.

    La normalización final del identificador se mantiene alineada con
    `issue_token`, que valida el contrato de autenticación.
    """
    token, expires = issue_token(payload.sub)
    return SessionResponse(
        token=token,
        sub=payload.sub.strip(),
        expiresAt=expires.isoformat(),
    )
