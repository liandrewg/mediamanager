import sqlite3
import unittest

from app.services.analytics_service import get_analytics, get_sla_target_simulation


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

    def test_recommended_sla_is_inferred_from_fulfillment_history(self):
        analytics = get_analytics(self.conn, sla_days=7)

        self.assertEqual(analytics["recommended_sla_days"], 8)
        self.assertEqual(analytics["recommended_sla_within_rate"], 50.0)
        self.assertEqual(analytics["recommended_sla_sample_size"], 2)
        self.assertIsNotNone(analytics["open_breaching_recommended_sla"])

    def test_sla_target_simulation_compares_multiple_targets(self):
        simulation = get_sla_target_simulation(self.conn, [3, 7, 12], current_target_days=7)

        self.assertEqual(simulation["historical_sample_size"], 2)
        self.assertEqual(simulation["open_sample_size"], 1)
        self.assertEqual(simulation["current_target_days"], 7)
        self.assertEqual([row["target_days"] for row in simulation["scenarios"]], [3, 7, 12])

        seven_day = next(row for row in simulation["scenarios"] if row["target_days"] == 7)
        self.assertEqual(seven_day["historical_hit_rate"], 50.0)
        self.assertEqual(seven_day["open_breaching"], 1)
        self.assertEqual(seven_day["delta_vs_current"]["open_breaching"], 0)
        self.assertIn("operational_risk_score", seven_day)

        self.assertIn(simulation["recommended_target_days"], [3, 7, 12])


if __name__ == "__main__":
    unittest.main()
