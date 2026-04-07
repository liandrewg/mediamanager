import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

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

    def test_media_type_sla_insights_include_recommendations_and_open_risk(self):
        analytics = get_analytics(self.conn, sla_days=7)

        insights = {row["media_type"]: row for row in analytics["media_type_sla_insights"]}
        self.assertIn("movie", insights)
        self.assertIn("tv", insights)

        movie = insights["movie"]
        self.assertEqual(movie["fulfilled_sample_size"], 1)
        self.assertEqual(movie["recommended_target_days"], 2)
        self.assertEqual(movie["open_count"], 1)
        self.assertGreaterEqual(movie["open_breaching_global_policy"], 1)

        tv = insights["tv"]
        self.assertEqual(tv["fulfilled_sample_size"], 1)
        self.assertEqual(tv["recommended_target_days"], 10)
        self.assertEqual(tv["open_count"], 0)

    def test_weekly_sla_momentum_reports_trend_direction(self):
        now = datetime.now(timezone.utc)
        old_created = (now - timedelta(days=30)).isoformat()
        old_fulfilled = (now - timedelta(days=28)).isoformat()  # within 7-day SLA
        new_created = (now - timedelta(days=5)).isoformat()
        new_fulfilled = now.isoformat()  # outside 3-day SLA below

        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u4', 'drew', 1004, 'movie', 'Weekly Good', 'fulfilled', ?, ?)
            """,
            (old_created, old_fulfilled),
        )
        self.conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at)
            VALUES (4, 'approved', 'fulfilled', 'admin', '', ?)
            """,
            (old_fulfilled,),
        )

        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u5', 'erin', 1005, 'tv', 'Weekly Bad', 'fulfilled', ?, ?)
            """,
            (new_created, new_fulfilled),
        )
        self.conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at)
            VALUES (5, 'approved', 'fulfilled', 'admin', '', ?)
            """,
            (new_fulfilled,),
        )
        self.conn.commit()

        analytics = get_analytics(self.conn, sla_days=3)
        self.assertGreaterEqual(len(analytics["weekly_sla_hit_rate"]), 2)
        self.assertIn(analytics["sla_trend_direction"], ["improving", "flat", "regressing"])
        self.assertIsInstance(analytics["sla_trend_delta"], float)


if __name__ == "__main__":
    unittest.main()
