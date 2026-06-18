"""Playwright-based fetcher for ESPN soccer pages.

Loads the *rendered* page (navigate, wait for JS to render, read the DOM) and returns
the resulting HTML. Rendered HTML is cached to disk so re-runs and parser development
never re-hit ESPN. We deliberately scrape the rendered DOM rather than any JSON feed.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from types import TracebackType
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PWTimeoutError, sync_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import ESPN_BASE, LEAGUE_SLUG, settings

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def scoreboard_url(date_yyyymmdd: str) -> str:
    return f"{ESPN_BASE}/soccer/scoreboard/_/league/{LEAGUE_SLUG}/date/{date_yyyymmdd}"


def schedule_url(year: int) -> str:
    # NOTE: ESPN ignores the season arg here; kept for reference only. Discovery uses
    # scoreboard_url() day-by-day instead.
    return f"{ESPN_BASE}/soccer/schedule/_/league/{LEAGUE_SLUG}/season/{year}"


def lineups_url(game_id: str) -> str:
    return f"{ESPN_BASE}/soccer/lineups/_/gameId/{game_id}"


def matchstats_url(game_id: str) -> str:
    return f"{ESPN_BASE}/soccer/matchstats/_/gameId/{game_id}"


def _cache_path(cache_dir: Path, url: str) -> Path:
    """Stable, filesystem-safe cache filename for a URL."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", url.split("espn.com/")[-1]).strip("-")[:80]
    return cache_dir / f"{slug}-{digest}.html"


class ESPNBrowser:
    """Context manager owning one headless Chromium context for the whole run."""

    def __init__(self, *, use_cache: bool = True) -> None:
        self._use_cache = use_cache
        self._pw = None
        self._browser = None
        self._context = None
        settings.cache_dir.mkdir(parents=True, exist_ok=True)

    def __enter__(self) -> "ESPNBrowser":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=settings.headless)
        self._context = self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 900},
        )
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    @retry(
        retry=retry_if_exception_type(PWTimeoutError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    def _render(self, url: str, wait_selector: str) -> str:
        assert self._context is not None
        page: Page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            # Wait for the JS-rendered content we actually care about. Tolerate its
            # absence (some old matches never render a full lineup) and parse what's there.
            try:
                page.wait_for_selector(wait_selector, timeout=15_000)
            except PWTimeoutError:
                pass
            # ESPN lazy-loads lineup/bench content on scroll, so nudge the page and settle.
            for _ in range(6):
                page.mouse.wheel(0, 3500)
                page.wait_for_timeout(400)
            html = page.content()
        finally:
            page.close()
        time.sleep(settings.request_delay)  # be polite
        return html

    # Real ESPN pages render to hundreds of KB; anything tiny is a failed/partial render
    # that we must not persist (a poisoned cache entry would silently drop matches).
    _MIN_CACHEABLE_BYTES = 50_000

    def fetch(self, url: str, wait_selector: str = "body") -> str:
        """Return rendered HTML for a URL, using the disk cache when available."""
        cache_file = _cache_path(settings.cache_dir, url)
        if self._use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

        html = self._render(url, wait_selector)
        if len(html) >= self._MIN_CACHEABLE_BYTES:
            cache_file.write_text(html, encoding="utf-8")
        return html
