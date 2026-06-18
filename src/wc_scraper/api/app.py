"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import routes_admin, routes_read
from .db import close_pool, open_pool
from .ratelimit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    try:
        yield
    finally:
        close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="World Cup API",
        version="0.1.0",
        description="Read access to FIFA World Cup player stats. Writes require an API key.",
        lifespan=lifespan,
    )
    app.add_middleware(RateLimitMiddleware)
    app.include_router(routes_read.router)
    app.include_router(routes_admin.router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
