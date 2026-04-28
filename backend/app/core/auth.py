"""Autenticación de favoritos basada en tokens firmados.

Sustituye al `X-User-Id` opaco previo. El cliente ahora envía
`Authorization: Bearer <token>` (o `X-Session-Token: <token>` como alias) y
el servidor valida un JWT mínimo firmado con HS256 que contiene:

    {
      "sub": "<user_id>",        # identificador opaco interno
      "iat": 1714123456,         # epoch s de emisión
      "exp": 1716715456          # epoch s de expiración (default 30 días)
    }

Decisiones:
- HS256 con secreto compartido (`FAVORITES_SECRET`). Es suficiente para un
  servicio mono-instancia con clientes propios; no compensa la complejidad
  de RS256/JWKS hasta que haya terceros emisores.
- TTL de 30 días por defecto: balance entre conveniencia (no obligar al
  usuario a renovar diariamente) y blast radius si se filtra un token.
- Endpoint `POST /auth/session` que emite el token a partir de un id de
  cliente (p. ej. el device id del cliente Flutter, o un correo). En esta
  fase la emisión confía en lo que envía el cliente (es el mismo modelo de
  trust del `X-User-Id` previo, pero ahora el cliente NO PUEDE forjar la
  identidad de otro a partir de su token: necesita la clave secreta para
  re-firmar). Cuando haya una capa de identidad real (OAuth/OIDC) se
  delegará la verificación previa allí y este endpoint quedará para
  intercambios server-to-server.
- Si `FAVORITES_SECRET` no está definido, emitir o validar tokens provoca 503
  (fail-closed). La clave debe configurarse explícitamente en cada entorno.

Validaciones adicionales sobre el `sub`:
- mismas reglas de chars seguros que el `X-User-Id` previo (no `:*?[]` ni
  whitespace) para que la clave Redis `user:{sub}:favorites` no se pueda
  romper.
- longitud máxima 128 chars.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)


# Caracteres prohibidos en el sub: los que romperían la clave de Redis
# (`:` separa segmentos, `*?[]` son comodines de KEYS/SCAN) más whitespace.
_FORBIDDEN_SUB_CHARS = frozenset(":*?[] \t\n\r")
_SUB_MAX_LEN = 128
_JWT_ALGORITHM = "HS256"
_DEFAULT_TTL_DAYS = 30


def _resolve_secret() -> Optional[str]:
    """Devuelve la clave de firma. None si no está configurada."""
    raw = (os.getenv("FAVORITES_SECRET") or "").strip()
    return raw or None


def _validate_sub(sub: str) -> str:
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
            detail="sub contiene caracteres inválidos (espacios o ':*?[]')",
        )
    return sub


def issue_token(sub: str, *, ttl_days: int = _DEFAULT_TTL_DAYS) -> tuple[str, datetime]:
    """Firma un JWT para `sub`. Devuelve `(token, expira_en_utc)`."""
    secret = _resolve_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="Auth no configurada: definir FAVORITES_SECRET",
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
    """Decodifica y valida firma + expiración. Devuelve los claims o lanza 401."""
    secret = _resolve_secret()
    if secret is None:
        raise HTTPException(
            status_code=503,
            detail="Auth no configurada: definir FAVORITES_SECRET",
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
    """Localiza el token: `Authorization: Bearer X` o `X-Session-Token: X`."""
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
        raise HTTPException(
            status_code=401,
            detail="Cabecera Authorization mal formada (esperado 'Bearer <token>')",
        )
    if session_token and session_token.strip():
        return session_token.strip()
    raise HTTPException(
        status_code=401,
        detail="Falta token (Authorization: Bearer ... o X-Session-Token)",
    )


def require_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
) -> str:
    """Dependency de FastAPI: devuelve el `sub` validado.

    Es la sustituta directa de `require_user_id`: el favoritos router solo
    cambia el import.
    """
    token = _extract_token(authorization, session_token)
    claims = _decode(token)
    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Token sin sub")
    return _validate_sub(sub)
