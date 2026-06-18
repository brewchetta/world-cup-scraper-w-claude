"""Runtime configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ESPN_BASE = "https://www.espn.com"
# ESPN's league slug for the men's FIFA World Cup.
LEAGUE_SLUG = "fifa.world"

# ESPN's /schedule/season/{year} endpoint ignores the year, so we discover matches by
# walking the scoreboard day-by-day. These are the (inclusive) date windows per men's
# World Cup, padded slightly. Note 2022 was a November-December tournament.
TOURNAMENT_WINDOWS: dict[int, tuple[str, str]] = {
    1970: ("1970-05-31", "1970-06-21"),
    1974: ("1974-06-13", "1974-07-07"),
    1978: ("1978-06-01", "1978-06-25"),
    1982: ("1982-06-13", "1982-07-11"),
    1986: ("1986-05-31", "1986-06-29"),
    1990: ("1990-06-08", "1990-07-08"),
    1994: ("1994-06-17", "1994-07-17"),
    1998: ("1998-06-10", "1998-07-12"),
    2002: ("2002-05-31", "2002-06-30"),
    2006: ("2006-06-09", "2006-07-09"),
    2010: ("2010-06-11", "2010-07-11"),
    2014: ("2014-06-12", "2014-07-13"),
    2018: ("2018-06-14", "2018-07-15"),
    2022: ("2022-11-20", "2022-12-18"),
    2026: ("2026-06-11", "2026-07-19"),
}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    headless: bool
    request_delay: float
    cache_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            headless=_as_bool(os.getenv("WC_HEADLESS"), True),
            request_delay=float(os.getenv("WC_REQUEST_DELAY", "1.5")),
            cache_dir=Path(os.getenv("WC_CACHE_DIR", ".cache")),
        )


settings = Settings.from_env()
