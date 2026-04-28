"""Tests for the request preflight service.

The preflight feature needs to give a requester a transparent picture of
what would happen *before* they click "request": is it already on the
server? does someone else already have it pending? was it added recently?
This suite locks down the four primary verdicts (watch_now,
already_supporting, join_queue, fresh_request) plus the recently-added
shortcut, and the queue-position math for approved community requests.
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import request_service


SCHEMA = """
CREATE TABLE requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    tmdb_id INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    title TEXT NOT NULL,
    poster_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    admin_note TEXT,
    jellyfin_item_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE request_supporters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(request_id, user_id)
);

CREATE TABLE request_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sla_policy (
    id INTEGER PRIMARY KEY,
    target_days INTEGER NOT NULL,
    warning_days INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO sla_policy (id, target_days, warning_days) VALUES (1, 7, 2)"
    )
    return conn


def insert_request(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    username: str,
    tmdb_id: int,
    media_type: str = "movie",
    title: str = "Title",
    status: str = "pending",
    days_ago: int = 0,
    jellyfin_item_id: str | None = None,
) -> int:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    cursor = conn.execute(
        """
        INSERT INTO requests
            (user_id, username, tmdb_id, media_type, title, status,
             jellyfin_item_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            tmdb_id,
            media_type,
            title,
            status,
            jellyfin_item_id,
            created.isoformat(),
            created.isoformat(),
        ),
    )
    request_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO request_supporters (request_id, user_id, username, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (request_id, user_id, username, created.isoformat()),
    )
    conn.commit()
    return request_id


# ---------------------------------------------------------------------------
# Verdict: watch_now
# ---------------------------------------------------------------------------
def test_watch_now_when_in_library_returns_watch_url_and_disables_request():
    conn = make_db()
    payload = request_service.compute_preflight(
        conn,
        tmdb_id=99,
        media_type="movie",
        user_id="alice",
        in_library=True,
        library_jellyfin_item_id="jf-abc",
    )
    assert payload["in_library"] is True
    assert payload["library_watch_url"] is not None
    assert "jf-abc" in payload["library_watch_url"]
    verdict = payload["verdict"]
    assert verdict["code"] == "watch_now"
    assert verdict["request_disabled"] is True
    assert verdict["primary_action"] == "watch"


# ---------------------------------------------------------------------------
# Verdict: already_supporting / is_owner
# ---------------------------------------------------------------------------
def test_already_supporting_when_user_owns_existing_pending_request():
    conn = make_db()
    insert_request(
        conn,
        user_id="alice",
        username="alice",
        tmdb_id=42,
        status="pending",
        days_ago=2,
    )
    payload = request_service.compute_preflight(
        conn,
        tmdb_id=42,
        media_type="movie",
        user_id="alice",
        in_library=False,
    )
    verdict = payload["verdict"]
    assert verdict["code"] == "already_supporting"
    assert verdict["request_disabled"] is True
    assert payload["community_request"]["is_owner"] is True
    assert payload["community_request"]["user_supporting"] is True


# ---------------------------------------------------------------------------
# Verdict: join_queue
# ---------------------------------------------------------------------------
def test_join_queue_when_other_user_has_open_request():
    conn = make_db()
    insert_request(
        conn,
        user_id="bob",
        username="bob",
        tmdb_id=42,
        status="pending",
        days_ago=1,
    )
    payload = request_service.compute_preflight(
        conn,
        tmdb_id=42,
        media_type="movie",
        user_id="alice",
        in_library=False,
    )
    verdict = payload["verdict"]
    assert verdict["code"] == "join_queue"
    assert verdict["primary_action"] == "join"
    assert verdict["request_disabled"] is False
    assert payload["community_request"]["supporter_count"] == 1
    assert payload["community_request"]["user_supporting"] is False
    assert payload["community_request"]["is_owner"] is False


# ---------------------------------------------------------------------------
# Verdict: fresh_request
# ---------------------------------------------------------------------------
def test_fresh_request_when_nothing_exists():
    conn = make_db()
    payload = request_service.compute_preflight(
        conn,
        tmdb_id=42,
        media_type="movie",
        user_id="alice",
        in_library=False,
    )
    verdict = payload["verdict"]
    assert verdict["code"] == "fresh_request"
    assert verdict["primary_action"] == "request"
    assert verdict["request_disabled"] is False
    assert payload["community_request"] is None
    assert payload["recently_fulfilled"] is None


# ---------------------------------------------------------------------------
# Recently fulfilled shortcut
# ---------------------------------------------------------------------------
def test_recently_fulfilled_within_30d_surfaces_recent_add_verdict():
    conn = make_db()
    # Create a fulfilled request from 5 days ago (no longer in OPEN status,
    # so it shouldn't appear as a community request).
    request_id = insert_request(
        conn,
        user_id="bob",
        username="bob",
        tmdb_id=99,
        status="fulfilled",
        days_ago=5,
        jellyfin_item_id="jf-xyz",
    )
    fulfilled_at = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    conn.execute(
        """
        INSERT INTO request_history
            (request_id, old_status, new_status, changed_by, created_at)
        VALUES (?, 'approved', 'fulfilled', 'admin', ?)
        """,
        (request_id, fulfilled_at),
    )
    conn.commit()

    payload = request_service.compute_preflight(
        conn,
        tmdb_id=99,
        media_type="movie",
        user_id="alice",
        in_library=False,
    )
    assert payload["recently_fulfilled"] is not None
    assert payload["recently_fulfilled"]["age_days"] == 5
    assert payload["verdict"]["code"] == "recently_added"


def test_recently_fulfilled_older_than_30d_is_ignored():
    conn = make_db()
    request_id = insert_request(
        conn,
        user_id="bob",
        username="bob",
        tmdb_id=99,
        status="fulfilled",
        days_ago=120,
    )
    fulfilled_at = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    conn.execute(
        """
        INSERT INTO request_history
            (request_id, old_status, new_status, changed_by, created_at)
        VALUES (?, 'approved', 'fulfilled', 'admin', ?)
        """,
        (request_id, fulfilled_at),
    )
    conn.commit()

    payload = request_service.compute_preflight(
        conn,
        tmdb_id=99,
        media_type="movie",
        user_id="alice",
        in_library=False,
    )
    assert payload["recently_fulfilled"] is None
    assert payload["verdict"]["code"] == "fresh_request"


# ---------------------------------------------------------------------------
# Queue position math (approved requests)
# ---------------------------------------------------------------------------
def test_queue_position_counts_older_approved_requests():
    conn = make_db()
    # Two older approved requests (different titles), then ours.
    insert_request(
        conn, user_id="u1", username="u1", tmdb_id=1, status="approved", days_ago=10
    )
    insert_request(
        conn, user_id="u2", username="u2", tmdb_id=2, status="approved", days_ago=8
    )
    insert_request(
        conn, user_id="bob", username="bob", tmdb_id=42, status="approved", days_ago=3
    )

    payload = request_service.compute_preflight(
        conn,
        tmdb_id=42,
        media_type="movie",
        user_id="alice",
        in_library=False,
    )
    cr = payload["community_request"]
    assert cr is not None
    assert cr["status"] == "approved"
    # Two older approved requests ahead of ours -> position 3, queue size 3.
    assert cr["queue_size"] == 3
    assert cr["queue_position"] == 3


# ---------------------------------------------------------------------------
# Bad media_type
# ---------------------------------------------------------------------------
def test_unsupported_media_type_raises():
    conn = make_db()
    try:
        request_service.compute_preflight(
            conn,
            tmdb_id=1,
            media_type="podcast",
            user_id="alice",
            in_library=False,
        )
    except ValueError as exc:
        assert "Unsupported media_type" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported media_type")
