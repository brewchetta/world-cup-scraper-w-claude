"""Shared synchronous Postgres connection pool for the API.

FastAPI runs `def` route handlers in a threadpool, so a synchronous psycopg pool is the
simplest correct choice and matches the rest of the codebase.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import api_settings

_pool: Optional[ConnectionPool] = None


def open_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not api_settings.database_url:
            raise RuntimeError("DATABASE_URL is not set (see .env.example).")
        _pool = ConnectionPool(
            api_settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    pool = open_pool()
    with pool.connection() as conn:
        yield conn
