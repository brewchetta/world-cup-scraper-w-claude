"""`wc-api` CLI: run the server and manage API keys directly against the database."""

from __future__ import annotations

import typer
import uvicorn

from . import keys
from .config import api_settings

app = typer.Typer(add_completion=False, help="World Cup API server + key management.")


def _connect():
    url = api_settings.database_url
    if not url:
        typer.secho("DATABASE_URL is not set (see .env.example).", fg=typer.colors.RED)
        raise typer.Exit(1)
    import psycopg

    return psycopg.connect(url)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev)."),
):
    """Run the API with uvicorn."""
    uvicorn.run("wc_scraper.api.app:app", host=host, port=port, reload=reload)


@app.command("create-key")
def create_key_cmd(
    client_name: str = typer.Argument(..., help="Human label for the key owner."),
    admin: bool = typer.Option(False, "--admin", help="Create an admin (key-managing) key."),
):
    """Mint a new API key. The plaintext is shown once -- store it now."""
    with _connect() as conn:
        token = keys.create_key(conn, client_name, "admin" if admin else "client")
    typer.secho("Key created. Copy it now (it will not be shown again):", fg=typer.colors.GREEN)
    typer.echo(token)


@app.command("rotate-key")
def rotate_key_cmd(key_id: int):
    """Regenerate a key's secret in place; the old value stops working immediately."""
    with _connect() as conn:
        token = keys.rotate_key(conn, key_id)
    if token is None:
        typer.secho(f"No key with id {key_id}.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho("Key rotated. New value (shown once):", fg=typer.colors.GREEN)
    typer.echo(token)


@app.command("revoke-key")
def revoke_key_cmd(key_id: int):
    """Permanently disable a key."""
    with _connect() as conn:
        ok = keys.revoke_key(conn, key_id)
    if not ok:
        typer.secho(f"No active key with id {key_id}.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"Key {key_id} revoked.", fg=typer.colors.GREEN)


@app.command("list-keys")
def list_keys_cmd():
    """List keys (prefixes only; secrets are never stored)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, client_name, key_prefix, role, last_used_at, revoked_at "
            "FROM api_keys ORDER BY id"
        ).fetchall()
    if not rows:
        typer.echo("No keys yet.")
        return
    for r in rows:
        status = "revoked" if r[5] else "active"
        typer.echo(f"  #{r[0]} [{r[3]}/{status}] {r[1]} ({r[2]}...) last_used={r[4]}")


if __name__ == "__main__":
    app()
