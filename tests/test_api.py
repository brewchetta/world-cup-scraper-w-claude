"""API integration tests (require DATABASE_URL; run against the loaded Supabase data).

The bootstrap admin secret is set BEFORE importing the app so api config picks it up.
"""

from __future__ import annotations

import os

import pytest

BOOTSTRAP = "test-bootstrap-admin-secret"
os.environ.setdefault("BOOTSTRAP_ADMIN_KEY", BOOTSTRAP)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

if not os.getenv("DATABASE_URL"):
    pytest.skip("DATABASE_URL not set; skipping API integration tests", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from wc_scraper.api.app import create_app  # noqa: E402
from wc_scraper.api.ratelimit import _FixedWindowCounter  # noqa: E402

ADMIN_HEADER = {"Authorization": f"Bearer {BOOTSTRAP}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c
    # Clean up any keys these tests created.
    from wc_scraper.api.db import connection

    with connection() as conn:
        conn.execute("DELETE FROM api_keys WHERE client_name LIKE 'test-%%'")
        conn.commit()


# --- public reads ----------------------------------------------------------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_guest_can_list_tournaments(client):
    r = client.get("/tournaments")
    assert r.status_code == 200
    years = {t["year"] for t in r.json()}
    assert {2018, 2022} <= years


def test_match_detail_includes_player_stats(client):
    matches = client.get("/matches", params={"year": 2022, "limit": 1}).json()
    assert matches
    detail = client.get(f"/matches/{matches[0]['id']}").json()
    assert len(detail["stats"]) > 0
    assert "full_name" in detail["stats"][0]


# --- auth boundary ---------------------------------------------------------

def test_me_requires_key(client):
    assert client.get("/me").status_code == 401
    r = client.get("/me", headers=ADMIN_HEADER)
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_admin_creates_client_key_then_rotates(client):
    created = client.post(
        "/admin/keys", headers=ADMIN_HEADER, json={"client_name": "test-acme"}
    )
    assert created.status_code == 201
    body = created.json()
    key_id, token = body["id"], body["key"]

    # New client key works and reports the client role.
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["role"] == "client"

    # Rotation invalidates the old token and issues a new working one.
    rotated = client.post(f"/admin/keys/{key_id}/rotate", headers=ADMIN_HEADER).json()
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get(
        "/me", headers={"Authorization": f"Bearer {rotated['key']}"}
    ).status_code == 200


def test_client_key_cannot_manage_keys(client):
    token = client.post(
        "/admin/keys", headers=ADMIN_HEADER, json={"client_name": "test-limited"}
    ).json()["key"]
    r = client.get("/admin/keys", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_invalid_key_is_unauthorized(client):
    assert client.get("/me", headers={"Authorization": "Bearer wc_live_not_real"}).status_code == 401


# --- rate limiter (unit; deterministic, no network) ------------------------

def test_fixed_window_counter_allows_then_blocks():
    counter = _FixedWindowCounter()
    now = 1_000_000.0  # fixed timestamp -> single window
    allowed = [counter.hit("ip:x", limit=3, now=now)[0] for _ in range(4)]
    assert allowed == [True, True, True, False]
    # A different identity has its own bucket.
    assert counter.hit("ip:y", limit=3, now=now)[0] is True
