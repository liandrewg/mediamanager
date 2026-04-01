import sqlite3
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import require_admin
from app.routers import admin


class ApplyRecommendedSlaPolicyRouteTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE sla_policy (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_days INTEGER NOT NULL DEFAULT 7 CHECK (target_days >= 1),
                warning_days INTEGER NOT NULL DEFAULT 2 CHECK (warning_days >= 0),
                updated_at TEXT
            );

            INSERT INTO sla_policy (id, target_days, warning_days, updated_at)
            VALUES (1, 6, 2, '2026-03-30T00:00:00+00:00');
            """
        )

        self.app = FastAPI()
        self.app.include_router(admin.router, prefix="/api/admin")

        def override_db():
            yield self.conn

        async def override_admin():
            return {"user_id": "admin-1", "is_admin": True}

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[require_admin] = override_admin
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.conn.close()

    @patch("app.services.analytics_service.get_analytics")
    def test_apply_recommended_sla_policy_persists_recommended_target(self, mock_get_analytics):
        mock_get_analytics.return_value = {
            "recommended_sla_days": 4,
            "recommended_sla_within_rate": 75.0,
            "recommended_sla_sample_size": 8,
        }

        response = self.client.post("/api/admin/sla-policy/apply-recommended", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target_days"], 4)
        self.assertEqual(response.json()["warning_days"], 2)
        self.assertEqual(mock_get_analytics.call_args.kwargs["sla_days"], 6)

        row = self.conn.execute("SELECT target_days, warning_days FROM sla_policy WHERE id = 1").fetchone()
        self.assertEqual(row["target_days"], 4)
        self.assertEqual(row["warning_days"], 2)

    @patch("app.services.analytics_service.get_analytics")
    def test_apply_recommended_sla_policy_caps_warning_override_via_saved_policy(self, mock_get_analytics):
        mock_get_analytics.return_value = {
            "recommended_sla_days": 3,
            "recommended_sla_within_rate": 66.7,
            "recommended_sla_sample_size": 6,
        }

        response = self.client.post(
            "/api/admin/sla-policy/apply-recommended",
            json={"warning_days_override": 99},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target_days"], 3)
        self.assertEqual(response.json()["warning_days"], 2)

    @patch("app.services.analytics_service.get_analytics")
    def test_apply_recommended_sla_policy_returns_400_when_no_recommendation_exists(self, mock_get_analytics):
        mock_get_analytics.return_value = {
            "recommended_sla_days": None,
            "recommended_sla_within_rate": None,
            "recommended_sla_sample_size": 0,
        }

        response = self.client.post("/api/admin/sla-policy/apply-recommended", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "No recommended SLA is available yet. Fulfill at least one request first.",
        )
        self.assertEqual(mock_get_analytics.call_args.kwargs["sla_days"], 6)

        row = self.conn.execute("SELECT target_days, warning_days FROM sla_policy WHERE id = 1").fetchone()
        self.assertEqual(row["target_days"], 6)
        self.assertEqual(row["warning_days"], 2)


class SimulateSlaTargetsRouteTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
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

            CREATE TABLE sla_policy (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_days INTEGER NOT NULL DEFAULT 7 CHECK (target_days >= 1),
                warning_days INTEGER NOT NULL DEFAULT 2 CHECK (warning_days >= 0),
                updated_at TEXT
            );

            INSERT INTO sla_policy (id, target_days, warning_days, updated_at)
            VALUES (1, 7, 2, '2026-03-30T00:00:00+00:00');
            """
        )

        self.app = FastAPI()
        self.app.include_router(admin.router, prefix="/api/admin")

        def override_db():
            yield self.conn

        async def override_admin():
            return {"user_id": "admin-1", "is_admin": True}

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[require_admin] = override_admin
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.conn.close()

    def test_rejects_invalid_target_tokens(self):
        response = self.client.get('/api/admin/sla-policy/simulate?targets=7,abc')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid SLA target: abc")

    def test_simulation_includes_current_target_and_recommendation_metadata(self):
        response = self.client.get('/api/admin/sla-policy/simulate?targets=3,7,10')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["current_target_days"], 7)
        self.assertIn(body["recommended_target_days"], [3, 7, 10])
        self.assertEqual(len(body["scenarios"]), 3)
        self.assertIn("operational_risk_score", body["scenarios"][0])


if __name__ == "__main__":
    unittest.main()
