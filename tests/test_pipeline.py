"""Unit tests for recent-date selection in the pipeline (no network)."""

from __future__ import annotations

import re
from datetime import date

from wc_scraper import pipeline


class _FakeBrowser:
    """Records fetched URLs; returns empty HTML so discovery finds no gameIds."""

    def __init__(self) -> None:
        self.fetched: list[str] = []

    def fetch(self, url: str, wait_selector: str = "body") -> str:
        self.fetched.append(url)
        return "<html><body></body></html>"


def _dates_fetched(browser: _FakeBrowser) -> list[str]:
    return [m.group(1) for u in browser.fetched if (m := re.search(r"/date/(\d{8})", u))]


def test_recent_picks_today_and_prior_day_within_window():
    b = _FakeBrowser()
    pipeline.run_recent(b, days=1, conn=None, today=date(2026, 6, 18))
    assert _dates_fetched(b) == ["20260617", "20260618"]


def test_recent_clips_to_window_start():
    # 2026 window starts 2026-06-11, so the prior day (06-10) is excluded.
    b = _FakeBrowser()
    pipeline.run_recent(b, days=1, conn=None, today=date(2026, 6, 11))
    assert _dates_fetched(b) == ["20260611"]


def test_recent_offseason_scrapes_nothing():
    b = _FakeBrowser()
    result = pipeline.run_recent(b, days=3, conn=None, today=date(2025, 1, 1))
    assert result == []
    assert b.fetched == []
