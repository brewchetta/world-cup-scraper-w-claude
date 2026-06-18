"""Command-line interface: `wc-scrape initdb` and `wc-scrape run`."""

from __future__ import annotations

import sys
from typing import Optional

import typer

from .config import settings
from .espn_client import ESPNBrowser
from . import pipeline

app = typer.Typer(add_completion=False, help="FIFA World Cup scraper (ESPN -> Postgres).")


def _require_db():
    if not settings.database_url:
        typer.secho("DATABASE_URL is not set (see .env.example).", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    from .db import loader

    return loader, loader.connect(settings.database_url)


@app.command()
def initdb() -> None:
    """Create the schema (tables + views) in the configured database."""
    loader, conn = _require_db()
    with conn:
        loader.init_db(conn)
    typer.secho("Schema created.", fg=typer.colors.GREEN)


@app.command()
def run(
    year: Optional[int] = typer.Option(None, help="Scrape a single tournament year."),
    game: Optional[str] = typer.Option(None, help="Scrape a single ESPN gameId."),
    all: bool = typer.Option(False, "--all", help="Scrape all years 1970..present."),
    load: bool = typer.Option(True, help="Load results into the database."),
    headless: Optional[bool] = typer.Option(
        None, help="Override headless mode (use --no-headless to watch)."
    ),
) -> None:
    """Scrape matches and (optionally) load them into the database."""
    if headless is not None:
        object.__setattr__(settings, "headless", headless)

    conn = None
    loader = None
    if load:
        loader, conn = _require_db()

    if not (year or game or all):
        typer.secho("Specify --year, --game, or --all.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    with ESPNBrowser() as browser:
        if game:
            # Single match: year is only used for the tournament row; default to 0 if unknown.
            scrape = pipeline.scrape_match(browser, game, year or 0)
            typer.echo(_format_scrape(scrape))
            if conn is not None:
                loader.load_match(conn, scrape)
        else:
            years = pipeline.TOURNAMENT_YEARS if all else [year]
            for y in years:
                pipeline.run_year(browser, y, conn=conn)

    if conn is not None:
        conn.close()


def _format_scrape(scrape) -> str:
    m = scrape.match
    lines = [f"{m.home_team} {m.home_score}-{m.away_score} {m.away_team}  ({m.round or '?'})"]
    for s in scrape.stats:
        mins = f"{s.minutes_played}'" if s.minutes_played is not None else "-"
        lines.append(
            f"  #{s.jersey_number or '?':<3} {s.full_name:<28} {s.team_name:<16} "
            f"G:{s.goals or 0} F:{s.fouls_committed if s.fouls_committed is not None else '-'} "
            f"min:{mins}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    app()
