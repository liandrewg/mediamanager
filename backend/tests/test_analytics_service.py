import sqlite3
import unittest

from app.services.analytics_service import get_analytics


class AnalyticsSlaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                tmdb_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                admin_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE request_supporters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT
            );
            """
        )

        # Fulfilled in 2 days (within SLA)
        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u1', 'alice', 1001, 'movie', 'Fast Fulfill', 'fulfilled', '2026-03-01T00:00:00+00:00', '2026-03-03T00:00:00+00:00')
            """
        )
        self.conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at)
            VALUES (1, 'approved', 'fulfilled', 'admin', '', '2026-03-03T00:00:00+00:00')
            """
        )

        # Fulfilled in 10 days (outside SLA)
        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u2', 'bob', 1002, 'tv', 'Slow Fulfill', 'fulfilled', '2026-03-01T00:00:00+00:00', '2026-03-11T00:00:00+00:00')
            """
        )
        self.conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at)
            VALUES (2, 'approved', 'fulfilled', 'admin', '', '2026-03-11T00:00:00+00:00')
            """
        )

        # Open request that breaches 7-day SLA
        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u3', 'cara', 1003, 'movie', 'Open Old', 'pending', '2026-03-01T00:00:00+00:00', '2026-03-01T00:00:00+00:00')
            """
        )

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_sla_metrics_are_computed(self):
        analytics = get_analytics(self.conn, sla_days=7)

        self.assertEqual(analytics["sla_days"], 7)
        self.assertEqual(analytics["fulfilled_within_sla_count"], 1)
        self.assertEqual(analytics["fulfilled_outside_sla_count"], 1)
        self.assertEqual(analytics["fulfilled_within_sla_rate"], 50.0)
        self.assertGreaterEqual(analytics["open_breaching_sla"], 1)


if __name__ == "__main__":
    unittest.main()
