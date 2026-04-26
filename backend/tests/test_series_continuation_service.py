import asyncio
import sqlite3
import unittest
from datetime import datetime, timezone

from app.services import series_continuation_service as scs


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        CREATE TABLE request_supporters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(request_id, user_id)
        );

        CREATE TABLE series_continuation_snapshots (
            tmdb_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            poster_path TEXT,
            last_seen_seasons INTEGER NOT NULL DEFAULT 0,
            last_aired_seasons INTEGER NOT NULL DEFAULT 0,
            tmdb_status TEXT,
            last_air_date TEXT,
            fulfilled_at TIMESTAMP,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            dismissed_through INTEGER NOT NULL DEFAULT 0,
            dismissed_at TIMESTAMP,
            dismissed_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    return conn


def _insert_fulfilled_request(
    conn: sqlite3.Connection,
    *,
    tmdb_id: int,
    title: str,
    poster: str | None = None,
    fulfilled_at: str = "2026-01-15 10:00:00",
) -> int:
    cur = conn.execute(
        "INSERT INTO requests (user_id, username, tmdb_id, media_type, title, poster_path, status) "
        "VALUES (?, ?, ?, 'tv', ?, ?, 'fulfilled')",
        ("user1", "alice", tmdb_id, title, poster),
    )
    rid = cur.lastrowid
    conn.execute(
        "INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at) "
        "VALUES (?, 'approved', 'fulfilled', 'admin', 'fulfilled', ?)",
        (rid, fulfilled_at),
    )
    conn.commit()
    return rid


class CountAiredSeasonsTests(unittest.TestCase):
    def test_excludes_specials_and_unaired(self):
        details = {
            "name": "Show",
            "seasons": [
                {"season_number": 0, "episode_count": 5, "air_date": "2020-01-01"},
                {"season_number": 1, "episode_count": 10, "air_date": "2020-06-01"},
                {"season_number": 2, "episode_count": 10, "air_date": "2021-06-01"},
                {"season_number": 3, "episode_count": 10, "air_date": "2099-06-01"},
                {"season_number": 4, "episode_count": 0, "air_date": None},
            ],
        }
        total, aired, last = scs.count_aired_seasons(details)
        # season 4 has 0 episodes → ignored. Season 3 is in the future.
        self.assertEqual(total, 3)
        self.assertEqual(aired, 2)
        self.assertEqual(last, "2021-06-01")

    def test_falls_back_to_tmdb_summary(self):
        details = {"number_of_seasons": 4, "last_air_date": "2024-01-01", "seasons": []}
        total, aired, last = scs.count_aired_seasons(details)
        self.assertEqual(total, 4)
        self.assertEqual(aired, 4)
        self.assertEqual(last, "2024-01-01")


class SnapshotBaselineTests(unittest.TestCase):
    def test_first_snapshot_baselines_dismissed_through(self):
        conn = _make_conn()
        _insert_fulfilled_request(conn, tmdb_id=99, title="Severance")

        details = {
            "name": "Severance",
            "status": "Returning Series",
            "seasons": [
                {"season_number": 1, "episode_count": 9, "air_date": "2022-02-18"},
                {"season_number": 2, "episode_count": 10, "air_date": "2025-01-17"},
            ],
        }
        snap = scs.update_snapshot_from_tmdb(
            conn,
            tmdb_id=99,
            fulfilled_at="2026-01-15 10:00:00",
            title_fallback="Severance",
            poster_fallback=None,
            tmdb_details=details,
        )
        # First time we saw it: 2 aired, dismissed_through baselined to 2
        self.assertEqual(snap["last_aired_seasons"], 2)
        self.assertEqual(snap["dismissed_through"], 2)
        candidates = scs.list_radar_candidates(conn)
        self.assertEqual(candidates, [])

    def test_new_season_appears_on_radar(self):
        conn = _make_conn()
        _insert_fulfilled_request(conn, tmdb_id=99, title="Severance")

        # First check: 2 seasons aired.
        scs.update_snapshot_from_tmdb(
            conn,
            tmdb_id=99,
            fulfilled_at="2026-01-15 10:00:00",
            title_fallback="Severance",
            poster_fallback=None,
            tmdb_details={
                "name": "Severance",
                "seasons": [
                    {"season_number": 1, "episode_count": 9, "air_date": "2022-02-18"},
                    {"season_number": 2, "episode_count": 10, "air_date": "2025-01-17"},
                ],
            },
        )

        # Later check: 3 seasons aired.
        scs.update_snapshot_from_tmdb(
            conn,
            tmdb_id=99,
            fulfilled_at="2026-01-15 10:00:00",
            title_fallback="Severance",
            poster_fallback=None,
            tmdb_details={
                "name": "Severance",
                "seasons": [
                    {"season_number": 1, "episode_count": 9, "air_date": "2022-02-18"},
                    {"season_number": 2, "episode_count": 10, "air_date": "2025-01-17"},
                    {"season_number": 3, "episode_count": 10, "air_date": "2026-03-20"},
                ],
            },
        )

        candidates = scs.list_radar_candidates(conn)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["tmdb_id"], 99)
        self.assertEqual(candidates[0]["new_seasons"], 1)
        self.assertEqual(candidates[0]["last_aired_seasons"], 3)

    def test_open_request_excludes_from_radar(self):
        conn = _make_conn()
        _insert_fulfilled_request(conn, tmdb_id=99, title="Severance")
        scs.update_snapshot_from_tmdb(
            conn,
            tmdb_id=99,
            fulfilled_at="2026-01-15 10:00:00",
            title_fallback="Severance",
            poster_fallback=None,
            tmdb_details={
                "name": "Severance",
                "seasons": [
                    {"season_number": 1, "episode_count": 9, "air_date": "2022-02-18"},
                ],
            },
        )
        # Bump artificially to simulate a delta.
        conn.execute(
            "UPDATE series_continuation_snapshots SET last_aired_seasons = 2, dismissed_through = 1 WHERE tmdb_id = 99"
        )
        # Open follow-up request:
        conn.execute(
            "INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status) "
            "VALUES ('admin', 'admin', 99, 'tv', 'Severance', 'approved')"
        )
        conn.commit()
        self.assertEqual(scs.list_radar_candidates(conn), [])


class QueueAndDismissTests(unittest.TestCase):
    def test_queue_creates_approved_request_and_advances_dismissed(self):
        conn = _make_conn()
        _insert_fulfilled_request(conn, tmdb_id=42, title="Foundation")
        # Build a snapshot with 1 season already accounted for, 3 aired total.
        conn.execute(
            "INSERT INTO series_continuation_snapshots "
            "(tmdb_id, title, last_seen_seasons, last_aired_seasons, dismissed_through) "
            "VALUES (42, 'Foundation', 3, 3, 1)"
        )
        conn.commit()

        result = scs.queue_continuation(
            conn, tmdb_id=42, admin_user_id="admin1", admin_username="andrew"
        )

        self.assertEqual(result["new_seasons"], 2)
        self.assertEqual(result["queued_through_seasons"], 3)

        # Verify the request was inserted as approved.
        req = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (result["request_id"],)
        ).fetchone()
        self.assertIsNotNone(req)
        self.assertEqual(req["status"], "approved")
        self.assertEqual(req["media_type"], "tv")
        self.assertIn("new season", req["admin_note"])

        # History entry exists.
        hist = conn.execute(
            "SELECT * FROM request_history WHERE request_id = ?", (result["request_id"],)
        ).fetchone()
        self.assertIsNotNone(hist)
        self.assertEqual(hist["new_status"], "approved")

        # Dismissed_through advanced.
        snap = conn.execute(
            "SELECT * FROM series_continuation_snapshots WHERE tmdb_id = 42"
        ).fetchone()
        self.assertEqual(snap["dismissed_through"], 3)

        # Radar should now be empty for this title.
        self.assertEqual(scs.list_radar_candidates(conn), [])

    def test_queue_blocks_when_open_request_exists(self):
        conn = _make_conn()
        _insert_fulfilled_request(conn, tmdb_id=42, title="Foundation")
        conn.execute(
            "INSERT INTO series_continuation_snapshots "
            "(tmdb_id, title, last_seen_seasons, last_aired_seasons, dismissed_through) "
            "VALUES (42, 'Foundation', 3, 3, 1)"
        )
        conn.execute(
            "INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status) "
            "VALUES ('user2', 'bob', 42, 'tv', 'Foundation', 'pending')"
        )
        conn.commit()

        with self.assertRaises(ValueError):
            scs.queue_continuation(
                conn, tmdb_id=42, admin_user_id="admin1", admin_username="andrew"
            )

    def test_queue_blocks_when_no_new_seasons(self):
        conn = _make_conn()
        conn.execute(
            "INSERT INTO series_continuation_snapshots "
            "(tmdb_id, title, last_seen_seasons, last_aired_seasons, dismissed_through) "
            "VALUES (42, 'Foundation', 2, 2, 2)"
        )
        conn.commit()
        with self.assertRaises(ValueError):
            scs.queue_continuation(
                conn, tmdb_id=42, admin_user_id="admin1", admin_username="andrew"
            )

    def test_dismiss_sets_dismissed_through_to_aired(self):
        conn = _make_conn()
        conn.execute(
            "INSERT INTO series_continuation_snapshots "
            "(tmdb_id, title, last_seen_seasons, last_aired_seasons, dismissed_through) "
            "VALUES (42, 'Foundation', 3, 3, 1)"
        )
        conn.commit()
        result = scs.dismiss_continuation(conn, tmdb_id=42, admin_user_id="admin1")
        self.assertEqual(result["dismissed_through"], 3)


class RefreshRadarTests(unittest.TestCase):
    def test_refresh_skips_titles_with_no_fulfilled_history(self):
        conn = _make_conn()
        # Pending request, never fulfilled.
        conn.execute(
            "INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status) "
            "VALUES ('user1', 'alice', 7, 'tv', 'Pending Show', 'pending')"
        )
        conn.commit()

        async def fetch(_id):
            self.fail("should not call TMDB when there are no fulfilled titles")

        result = asyncio.run(scs.refresh_radar(conn, fetch))
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["candidates"], 0)

    def test_refresh_handles_tmdb_error_gracefully(self):
        conn = _make_conn()
        _insert_fulfilled_request(conn, tmdb_id=11, title="Bad Show")

        async def fetch(_id):
            raise RuntimeError("TMDB exploded")

        result = asyncio.run(scs.refresh_radar(conn, fetch))
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["checked"], 0)


if __name__ == "__main__":
    unittest.main()
