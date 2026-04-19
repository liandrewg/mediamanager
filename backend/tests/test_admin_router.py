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


class RequesterDigestPackRouteTests(unittest.TestCase):
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
                poster_path TEXT,
                status TEXT NOT NULL,
                admin_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                jellyfin_item_id TEXT
            );

            CREATE TABLE request_supporters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(request_id, user_id)
            );

            CREATE TABLE request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                note TEXT,
                created_at TEXT
            );

            CREATE TABLE sla_policy (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_days INTEGER NOT NULL DEFAULT 7 CHECK (target_days >= 1),
                warning_days INTEGER NOT NULL DEFAULT 2 CHECK (warning_days >= 0),
                updated_at TEXT
            );

            INSERT INTO sla_policy (id, target_days, warning_days, updated_at)
            VALUES (1, 7, 2, '2026-04-01T00:00:00+00:00');

            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES
                ('u1', 'alice', 101, 'movie', 'Late Movie', 'pending', '2026-03-25T10:00:00+00:00', '2026-03-25T10:00:00+00:00'),
                ('u1', 'alice', 102, 'tv', 'Queued Show', 'approved', '2026-04-05T10:00:00+00:00', '2026-04-05T10:00:00+00:00'),
                ('u2', 'bob', 201, 'movie', 'Fresh Ask', 'pending', '2026-04-16T10:00:00+00:00', '2026-04-16T10:00:00+00:00');

            INSERT INTO request_supporters (request_id, user_id, username, created_at)
            VALUES
                (1, 'u1', 'alice', '2026-03-25T10:00:00+00:00'),
                (1, 'u3', 'cara', '2026-03-26T10:00:00+00:00'),
                (2, 'u1', 'alice', '2026-04-05T10:00:00+00:00'),
                (2, 'u4', 'dave', '2026-04-06T10:00:00+00:00'),
                (3, 'u2', 'bob', '2026-04-16T10:00:00+00:00');

            INSERT INTO requests (id, user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES
                (10, 'history-user', 'history', 910, 'movie', 'History A', 'fulfilled', '2026-04-01T10:00:00+00:00', '2026-04-04T10:00:00+00:00'),
                (11, 'history-user', 'history', 911, 'movie', 'History B', 'fulfilled', '2026-04-02T10:00:00+00:00', '2026-04-08T10:00:00+00:00');

            INSERT INTO request_supporters (request_id, user_id, username, created_at)
            VALUES
                (10, 'history-user', 'history', '2026-04-01T10:00:00+00:00'),
                (11, 'history-user', 'history', '2026-04-02T10:00:00+00:00');

            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at)
            VALUES
                (10, 'approved', 'fulfilled', 'admin-1', NULL, '2026-04-04T10:00:00+00:00'),
                (11, 'approved', 'fulfilled', 'admin-1', NULL, '2026-04-08T10:00:00+00:00');
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

    def test_requester_digest_pack_returns_grouped_digest_items(self):
        response = self.client.get('/api/admin/requester-digest-pack?limit=5')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['summary']['total'], 1)
        self.assertEqual(body['items'][0]['username'], 'alice')
        self.assertEqual(body['items'][0]['open_request_count'], 2)
        self.assertIn('Late Movie', body['items'][0]['request_titles'])


class RequestBlockerRouteTests(unittest.TestCase):
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
                poster_path TEXT,
                status TEXT NOT NULL,
                admin_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                jellyfin_item_id TEXT
            );
            CREATE TABLE request_supporters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(request_id, user_id)
            );
            CREATE TABLE request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                note TEXT,
                created_at TEXT
            );
            CREATE TABLE request_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                actor_user_id TEXT,
                actor_name TEXT,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE request_blockers (
                request_id INTEGER PRIMARY KEY,
                reason TEXT NOT NULL,
                note TEXT,
                review_on TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE sla_policy (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_days INTEGER NOT NULL DEFAULT 7,
                warning_days INTEGER NOT NULL DEFAULT 2,
                updated_at TEXT
            );
            INSERT INTO sla_policy (id, target_days, warning_days, updated_at)
            VALUES (1, 7, 2, '2026-04-01T00:00:00+00:00');
            INSERT INTO requests (id, user_id, username, tmdb_id, media_type, title, poster_path, status, created_at, updated_at)
            VALUES (1, 'u1', 'alice', 101, 'movie', 'Interstellar', NULL, 'approved', '2026-04-01T10:00:00+00:00', '2026-04-01T10:00:00+00:00');
            INSERT INTO request_supporters (request_id, user_id, username, created_at)
            VALUES (1, 'u1', 'alice', '2026-04-01T10:00:00+00:00');
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

    def test_can_set_and_clear_request_blocker(self):
        response = self.client.put(
            '/api/admin/requests/1/blocker',
            json={
                'reason': 'Waiting for upstream release',
                'review_on': '2026-04-20',
                'note': 'Check again after release day',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['blocker_reason'], 'Waiting for upstream release')

        review_loop = self.client.get('/api/admin/review-loop?limit=5')
        self.assertEqual(review_loop.status_code, 200)
        self.assertEqual(review_loop.json()['summary']['total'], 1)

        cleared = self.client.delete('/api/admin/requests/1/blocker')
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()['blocker_reason'])


if __name__ == "__main__":
    unittest.main()
