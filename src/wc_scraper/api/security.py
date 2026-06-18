"""Authentication dependencies: guests read, key-holders read+write, admins manage keys."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from . import keys
from .config import api_settings
from .db import connection


@dataclass(frozen=True)
class Principal:
    id: int            # 0 for the env bootstrap admin
    client_name: str
    role: str          # 'client' | 'admin'

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def extract_token(request: Request) -> Optional[str]:
    """Read the key from `Authorization: Bearer <key>` or the `X-API-Key` header."""
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


def resolve_principal(token: Optional[str]) -> Optional[Principal]:
    if not token:
        return None
    # Env bootstrap admin: a static credential to mint the first real keys.
    boot = api_settings.bootstrap_admin_key
    if boot and secrets.compare_digest(token, boot):
        return Principal(id=0, client_name="bootstrap-admin", role="admin")
    with connection() as conn:
        rec = keys.lookup_active(conn, token)
    if rec is None:
        return None
    return Principal(id=rec.id, client_name=rec.client_name, role=rec.role)


def get_optional_client(request: Request) -> Optional[Principal]:
    """No error if absent/invalid -- used by public read routes."""
    return resolve_principal(extract_token(request))


def require_client(
    principal: Optional[Principal] = Depends(get_optional_client),
) -> Principal:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid API key is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_admin(principal: Principal = Depends(require_client)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required.")
    return principal
