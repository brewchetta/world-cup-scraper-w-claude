"""Parse rendered ESPN HTML (visible DOM) into typed records.

We parse the human-visible elements only (no embedded JSON, no APIs). The stable hooks
are the player-profile links (``/soccer/player/_/id/{athleteId}/{slug}``) plus the sibling
text that shows the jersey number; everything else is best-effort because ESPN uses
randomized CSS class names and many fields simply are not shown for older matches.

Two layouts are handled:
  * Full squad layout (~2014+): a "Formations & Lineups" section that splits into two
    equal team subtrees. Yields the full named squad per team (name, athlete id, jersey).
  * Sparse layout (2010 and earlier): only a 6-player "key matchups" widget that pairs one
    home and one away player per row. Yields those few players (name, jersey, goals).

Missing values are returned as None rather than raising -- this is expected for old data.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import Match, MatchScrape, Player, PlayerMatchStat, Team

_PLAYER_HREF = re.compile(r"/soccer/player/_/id/(\d+)/([a-z0-9-]+)")
# "Netherlands 0-1 Spain (Jul 11, 2010) Final Score - ESPN"
_TITLE_RE = re.compile(r"^(?P<home>.+?)\s+(?P<hs>\d+)-(?P<as>\d+)\s+(?P<away>.+?)\s+\((?P<date>[^)]+)\)")


def _name_from_slug(slug: str) -> str:
    """'juan-fernando-quintero' -> 'Juan Fernando Quintero' (diacritics are lost)."""
    return " ".join(part.capitalize() for part in slug.split("-"))


def _athlete_from_anchor(a: Tag) -> Optional[tuple[int, str]]:
    m = _PLAYER_HREF.search(a.get("href", ""))
    if not m:
        return None
    return int(m.group(1)), _name_from_slug(m.group(2))


def _jersey_near(a: Tag) -> Optional[int]:
    """Jersey is the first number after the name, e.g. 'Munoz|2|1' -> 2 (the 1 is a goal)."""
    for container in (a.parent, a.parent.parent if a.parent else None):
        if container is None:
            continue
        text = container.get_text("|", strip=True)
        nums = re.findall(r"\b(\d{1,2})\b", text)
        if nums:
            return int(nums[0])
    return None


def _player_anchors(scope: Tag) -> list[Tag]:
    return [a for a in scope.find_all("a", href=True) if _PLAYER_HREF.search(a["href"])]


def parse_header(soup: BeautifulSoup) -> dict:
    title = soup.find("title")
    text = title.get_text(strip=True) if title else ""
    m = _TITLE_RE.match(text)
    if not m:
        return {"home": None, "away": None, "home_score": None, "away_score": None, "kickoff": None}
    kickoff = None
    try:
        kickoff = datetime.strptime(m.group("date"), "%b %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return {
        "home": m.group("home").strip(),
        "away": m.group("away").strip(),
        "home_score": int(m.group("hs")),
        "away_score": int(m.group("as")),
        "kickoff": kickoff,
    }


def _lineups_section(soup: BeautifulSoup) -> Optional[Tag]:
    """Smallest element containing the 'Formations & Lineups' heading and the squads.

    Scoping here matters: player links also appear in commentary/recirculation widgets,
    and we must not mistake those for lineup entries.
    """
    node = soup.find(string=re.compile(r"Formations\s*&\s*Lineups", re.I))
    if node is None:
        return None
    el = node.parent
    while el is not None and len(_player_anchors(el)) < 16:
        el = el.parent
    return el


def _team_sections(section: Tag) -> Optional[list[Tag]]:
    """Descend until a node's children split players into the two teams (>=8 each)."""
    node = section
    for _ in range(15):
        kids = [c for c in node.find_all(recursive=False) if isinstance(c, Tag)]
        kids_with = [(c, len(_player_anchors(c))) for c in kids]
        kids_with = [(c, n) for c, n in kids_with if n > 0]
        big = [c for c, n in kids_with if n >= 8]
        if len(big) >= 2:
            return big[:2]  # document order -> [home, away]
        if not kids_with:
            return None
        node = max(kids_with, key=lambda cn: cn[1])[0]
    return None


def _unique_players_in(section: Tag) -> list[tuple[int, str, Optional[int]]]:
    """(athlete_id, full_name, jersey) for each distinct player in a team section."""
    out: dict[int, tuple[int, str, Optional[int]]] = {}
    for a in _player_anchors(section):
        info = _athlete_from_anchor(a)
        if info is None:
            continue
        aid, name = info
        if aid not in out:
            out[aid] = (aid, name, _jersey_near(a))
    return list(out.values())


def _parse_full(soup: BeautifulSoup, header: dict, game_id: str, source_url: str) -> Optional[MatchScrape]:
    section = _lineups_section(soup)
    if section is None:
        return None
    teams_el = _team_sections(section)
    if not teams_el:
        return None

    team_names = [header["home"], header["away"]]
    players: list[Player] = []
    stats: list[PlayerMatchStat] = []
    for team_name, el in zip(team_names, teams_el):
        for aid, name, jersey in _unique_players_in(el):
            players.append(Player(full_name=name, espn_athlete_id=aid))
            stats.append(
                PlayerMatchStat(
                    espn_game_id=game_id,
                    team_name=team_name or "Unknown",
                    full_name=name,
                    espn_athlete_id=aid,
                    jersey_number=jersey,
                    source_url=source_url,
                )
            )
    if not stats:
        return None
    return _assemble(header, game_id, players, stats, team_names)


def _parse_sparse(soup: BeautifulSoup, header: dict, game_id: str, source_url: str) -> MatchScrape:
    """Old 'key matchups' widget: anchors alternate home, away, home, away, ..."""
    anchors = _player_anchors(soup)
    team_names = [header["home"], header["away"]]
    players: list[Player] = []
    stats: list[PlayerMatchStat] = []
    seen: set[int] = set()
    for idx, a in enumerate(anchors):
        info = _athlete_from_anchor(a)
        if info is None:
            continue
        aid, name = info
        if aid in seen:
            continue
        seen.add(aid)
        team_name = team_names[idx % 2] or "Unknown"
        # The matchup widget shows stat-comparison numbers, not shirt numbers, so jersey is
        # left null here. Goals are shown explicitly as "<n> G" and are reliable.
        own = a.get_text(" ", strip=True)
        goal_m = re.search(r"(\d+)\s*G\b", own)
        players.append(Player(full_name=name, espn_athlete_id=aid))
        stats.append(
            PlayerMatchStat(
                espn_game_id=game_id,
                team_name=team_name,
                full_name=name,
                espn_athlete_id=aid,
                jersey_number=None,
                goals=int(goal_m.group(1)) if goal_m else None,
                source_url=source_url,
            )
        )
    return _assemble(header, game_id, players, stats, team_names)


def _assemble(header, game_id, players, stats, team_names) -> MatchScrape:
    teams = [Team(name=n) for n in team_names if n]
    match = Match(
        espn_game_id=game_id,
        year=header.get("year") or (header["kickoff"].year if header.get("kickoff") else 0),
        kickoff_utc=header.get("kickoff"),
        home_team=header["home"] or "Unknown",
        away_team=header["away"] or "Unknown",
        home_score=header.get("home_score"),
        away_score=header.get("away_score"),
    )
    return MatchScrape(match=match, teams=teams, players=players, stats=stats)


def parse_match(
    *,
    game_id: str,
    year: int,
    lineups_html: str,
    matchstats_html: str,
    lineups_url: str,
) -> MatchScrape:
    soup = BeautifulSoup(lineups_html, "lxml")
    header = parse_header(soup)
    header["year"] = year or (header["kickoff"].year if header["kickoff"] else 0)

    full = _parse_full(soup, header, game_id, lineups_url)
    if full is not None:
        return full
    return _parse_sparse(soup, header, game_id, lineups_url)
