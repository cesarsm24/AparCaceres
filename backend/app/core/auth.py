"""Autenticación de favoritos mediante tokens de sesión firmados.

Proporciona emisión y validación de JWT con identificador opaco de usuario en
el claim `sub`. El token puede recibirse mediante `Authorization: Bearer` o
mediante `X-Session-Token` como cabecera alternativa.

La implementación usa firma simétrica HS256 y una clave configurada en
`FAVORITES_SECRET`. La ausencia de secreto bloquea la emisión y validación de
tokens para evitar aceptar sesiones sin una configuración explícita.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)


_FORBIDDEN_SUB_CHARS = frozenset(":*?[] \t\n\r")
_SUB_MAX_LEN = 128
_JWT_ALGORITHM = "HS256"
_DEFAULT_TTL_DAYS = 30


def _resolve_secret() -> Optional[str]:
    """Resuelve la clave de firma configurada para los tokens."""
    raw = (os.getenv("FAVORITES_SECRET") or "").strip()
    return raw or None


def _validate_sub(sub: str) -> str:
    """Normaliza y valida el identificador opaco usado como sujeto del token.

    El identificador se restringe para evitar claves Redis ambiguas o patrones
    que puedan interferir con operaciones de búsqueda.
    """
    sub = (sub or "").strip()

    if not sub:
        raise HTTPException(status_code=400, detail="sub vacío")

    if len(sub) > _SUB_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"sub excede {_SUB_MAX_LEN} caracteres",
        )

    if any(c in _FORBIDDEN_SUB_CHARS for c in sub):
        raise HTTPException(
            status_code=400,
            detail="sub contiene caracteres inválidos",
        )

    return sub


def issue_token(sub: str, *, ttl_days: int = _DEFAULT_TTL_DAYS) -> tuple[str, datetime]:
    """Emite un JWT para un identificador opaco validado.

    Devuelve el token firmado y su fecha de expiración en UTC.
    """
    secret = _resolve_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="Autenticación no configurada",
        )

    sub = _validate_sub(sub)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=ttl_days)

    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    token = jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)
    return token, exp


def _decode(token: str) -> dict:
    """Valida un JWT y devuelve sus claims."""
    secret = _resolve_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="Autenticación no configurada",
        )

    try:
        return jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expirado") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Token inválido") from exc


def _extract_token(
    authorization: Optional[str],
    session_token: Optional[str],
) -> str:
    """Extrae el token de sesión desde las cabeceras admitidas."""
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()

        raise HTTPException(
            status_code=401,
            detail="Cabecera Authorization mal formada",
        )

    if session_token and session_token.strip():
        return session_token.strip()

    raise HTTPException(status_code=401, detail="Falta token de sesión")


def require_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
) -> str:
    """Resuelve el usuario autenticado para dependencias de FastAPI."""
    token = _extract_token(authorization, session_token)
    claims = _decode(token)

    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Token sin sub")

    return _validate_sub(sub)