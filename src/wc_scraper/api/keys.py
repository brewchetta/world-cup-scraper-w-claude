"""API key generation, hashing, and lifecycle (create / rotate / revoke / lookup).

The plaintext key is returned to the caller exactly once (at create/rotate); the database
stores only its SHA-256 hash. Keys are high-entropy random tokens, so a fast hash is the
right tool (bcrypt is for low-entropy passwords).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

import psycopg

KEY_PREFIX = "wc_live_"
_PREFIX_DISPLAY_LEN = len(KEY_PREFIX) + 8  # store enough to identify a key at a glance


def generate_token() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class APIKeyRecord:
    id: int
    client_name: str
    role: str


def create_key(conn: psycopg.Connection, client_name: str, role: str = "client") -> str:
    """Insert a new key and return the one-time plaintext token."""
    token = generate_token()
    conn.execute(
        """
        INSERT INTO api_keys (client_name, key_prefix, key_hash, role)
        VALUES (%s, %s, %s, %s)
        """,
        (client_name, token[:_PREFIX_DISPLAY_LEN], hash_token(token), role),
    )
    conn.commit()
    return token


def rotate_key(conn: psycopg.Connection, key_id: int) -> Optional[str]:
    """Replace a key's secret in place; the old token stops working immediately."""
    token = generate_token()
    row = conn.execute(
        """
        UPDATE api_keys
        SET key_prefix = %s, key_hash = %s, revoked_at = NULL
        WHERE id = %s
        RETURNING id
        """,
        (token[:_PREFIX_DISPLAY_LEN], hash_token(token), key_id),
    ).fetchone()
    conn.commit()
    return token if row else None


def revoke_key(conn: psycopg.Connection, key_id: int) -> bool:
    row = conn.execute(
        "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL RETURNING id",
        (key_id,),
    ).fetchone()
    conn.commit()
    return row is not None


def lookup_active(conn: psycopg.Connection, token: str) -> Optional[APIKeyRecord]:
    """Resolve a plaintext token to an active key record, refreshing last_used_at."""
    row = conn.execute(
        """
        UPDATE api_keys SET last_used_at = now()
        WHERE key_hash = %s AND revoked_at IS NULL
        RETURNING id, client_name, role
        """,
        (hash_token(token),),
    ).fetchone()
    conn.commit()
    if not row:
        return None
    # dict_row is configured on the pool, but support tuple rows too (CLI connections).
    if isinstance(row, dict):
        return APIKeyRecord(row["id"], row["client_name"], row["role"])
    return APIKeyRecord(row[0], row[1], row[2])
