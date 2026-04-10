import sqlite3
import sys
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


def seed_request(conn: sqlite3.Connection, *, user_id: str, username: str, title: str, status: str, supporters: list[tuple[str, str]], created_at: str) -> None:
    cursor = conn.execute(
        """
        INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
        VALUES (?, ?, ?, 'movie', ?, ?, ?, ?)
        """,
        (user_id, username, len(title), title, status, created_at, created_at),
    )
    request_id = cursor.lastrowid
    for supporter_id, supporter_name in supporters:
        conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (?, ?, ?, ?)",
            (request_id, supporter_id, supporter_name, created_at),
        )
    conn.commit()


def test_user_requests_include_queue_transparency_details():
    conn = make_db()
    seed_request(
        conn,
        user_id="u1",
        username="Alice",
        title="Alpha",
        status="approved",
        supporters=[("u1", "Alice"), ("u4", "Drew")],
        created_at="2026-04-01T00:00:00+00:00",
    )
    seed_request(
        conn,
        user_id="u2",
        username="Bob",
        title="Beta",
        status="pending",
        supporters=[("u2", "Bob")],
        created_at="2026-04-02T00:00:00+00:00",
    )
    seed_request(
        conn,
        user_id="u3",
        username="Cara",
        title="Gamma",
        status="pending",
        supporters=[("u3", "Cara")],
        created_at="2026-04-03T00:00:00+00:00",
    )

    result = request_service.get_user_requests(conn, "u3", page=1, limit=10)
    req = result["items"][0]

    assert req["queue_position"] == 3
    assert req["queue_size"] == 3
    assert req["queue_ahead_count"] == 2
    assert req["approved_ahead_count"] == 1
    assert req["pending_ahead_count"] == 1
    assert req["supporters_ahead_count"] == 3
    assert req["queue_band"] == "near_front"
    assert req["queue_reason"] == "Only 2 requests ahead of you."
    assert req["blocker_label"] == "Ahead of you: 1 already approved, 1 still waiting for review, 3 total supporters ahead"


def test_first_in_line_request_gets_up_next_label():
    conn = make_db()
    seed_request(
        conn,
        user_id="u9",
        username="Nova",
        title="Solo",
        status="approved",
        supporters=[("u9", "Nova")],
        created_at="2026-04-01T00:00:00+00:00",
    )

    result = request_service.get_user_requests(conn, "u9", page=1, limit=10)
    req = result["items"][0]

    assert req["queue_position"] == 1
    assert req["queue_band"] == "up_next"
    assert req["queue_reason"] == "You are first in line right now."
    assert req["blocker_label"] is None
