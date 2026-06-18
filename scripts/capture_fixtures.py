"""(Re)capture the rendered-HTML fixtures the parser tests run against.

Run once (network required):
    ./.venv/Scripts/python.exe scripts/capture_fixtures.py

These three fixtures cover both ESPN layouts plus discovery:
  * scoreboard_20100711.html - a scoreboard-by-date page (discovery yields gameId 264123)
  * lineups_264123.html      - 2010 final, the sparse "key matchups" layout
  * lineups_760436.html      - 2026 group game, the full-squad layout
"""

from __future__ import annotations

from pathlib import Path

from wc_scraper.espn_client import ESPNBrowser, lineups_url, scoreboard_url

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

GAME_WAIT = "a[href*='/gameId/']"
PLAYER_WAIT = "a[href*='/soccer/player/']"

TARGETS = [
    ("scoreboard_20100711.html", scoreboard_url("20100711"), GAME_WAIT),
    ("lineups_264123.html", lineups_url("264123"), PLAYER_WAIT),
    ("lineups_760436.html", lineups_url("760436"), PLAYER_WAIT),
]


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with ESPNBrowser(use_cache=False) as browser:
        for filename, url, wait in TARGETS:
            print(f"Fetching {url}")
            html = browser.fetch(url, wait_selector=wait)
            (FIXTURES / filename).write_text(html, encoding="utf-8")
            print(f"  saved {filename} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
