"""Discover ESPN gameIds from a rendered scoreboard (or schedule) page."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_GAME_ID_RE = re.compile(r"/gameId/(\d+)")


def parse_schedule(html: str) -> list[str]:
    """Return de-duplicated gameIds (first-seen order) for the page's own matches.

    ESPN scoreboard pages render a "HeaderScoreboard" carousel of *other* matches (during
    a live tournament that means current-year games), which would otherwise leak into a
    historical date's results. We drop that carousel and read only the main scoreboard.
    """
    soup = BeautifulSoup(html, "lxml")
    for header in soup.select('[class*="HeaderScoreboard"]'):
        header.decompose()

    seen: dict[str, None] = {}
    for a in soup.select('a[href*="/gameId/"]'):
        m = _GAME_ID_RE.search(a.get("href", ""))
        if m:
            seen.setdefault(m.group(1), None)
    return list(seen.keys())
