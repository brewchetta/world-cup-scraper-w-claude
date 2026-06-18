"""Authenticated routes: key self-check (any client) and key management (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import keys
from .db import connection
from .schemas import ApiKeyCreatedOut, ApiKeyOut, WhoAmIOut
from .security import Principal, require_admin, require_client

router = APIRouter(tags=["admin"])


class CreateKeyIn(BaseModel):
    client_name: str
    role: str = "client"  # 'client' | 'admin'


@router.get("/me", response_model=WhoAmIOut)
def whoami(principal: Principal = Depends(require_client)):
    """Verify an API key and see its identity/role."""
    return WhoAmIOut(client_name=principal.client_name, role=principal.role)


@router.get("/admin/keys", response_model=list[ApiKeyOut])
def list_keys(_: Principal = Depends(require_admin)):
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, client_name, key_prefix, role, created_at, last_used_at, revoked_at
            FROM api_keys ORDER BY id
            """
        ).fetchall()


@router.post("/admin/keys", response_model=ApiKeyCreatedOut, status_code=201)
def create_key(body: CreateKeyIn, _: Principal = Depends(require_admin)):
    if body.role not in ("client", "admin"):
        raise HTTPException(400, "role must be 'client' or 'admin'")
    with connection() as conn:
        token = keys.create_key(conn, body.client_name, body.role)
        row = conn.execute(
            "SELECT id FROM api_keys WHERE key_hash = %s", (keys.hash_token(token),)
        ).fetchone()
    return ApiKeyCreatedOut(
        id=row["id"], client_name=body.client_name, role=body.role, key=token
    )


@router.post("/admin/keys/{key_id}/rotate", response_model=ApiKeyCreatedOut)
def rotate_key(key_id: int, _: Principal = Depends(require_admin)):
    with connection() as conn:
        token = keys.rotate_key(conn, key_id)
        if token is None:
            raise HTTPException(404, f"No key with id {key_id}")
        row = conn.execute(
            "SELECT client_name, role FROM api_keys WHERE id = %s", (key_id,)
        ).fetchone()
    return ApiKeyCreatedOut(
        id=key_id, client_name=row["client_name"], role=row["role"], key=token
    )


@router.delete("/admin/keys/{key_id}", status_code=204)
def revoke_key(key_id: int, _: Principal = Depends(require_admin)):
    with connection() as conn:
        if not keys.revoke_key(conn, key_id):
            raise HTTPException(404, f"No active key with id {key_id}")
