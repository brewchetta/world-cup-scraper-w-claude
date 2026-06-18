"""API configuration (env-driven), separate from the scraper settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class APISettings:
    database_url: str | None
    # Optional static admin credential used to bootstrap the first real admin key.
    bootstrap_admin_key: str | None
    # Tiered fixed-window rate limits (requests per minute).
    guest_rpm: int
    client_rpm: int

    @classmethod
    def from_env(cls) -> "APISettings":
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            bootstrap_admin_key=os.getenv("BOOTSTRAP_ADMIN_KEY") or None,
            guest_rpm=int(os.getenv("WC_API_GUEST_RPM", "30")),
            client_rpm=int(os.getenv("WC_API_CLIENT_RPM", "300")),
        )


api_settings = APISettings.from_env()
