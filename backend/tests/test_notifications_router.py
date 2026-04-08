import sqlite3
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.routers import notifications


class NotificationsRouterTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
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
                created_at TEXT,
                updated_at TEXT
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
                created_at TEXT NOT NULL
            );

            INSERT INTO requests (id, user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES (1, 'user-1', 'andrew', 101, 'movie', 'Interstellar', 'pending', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00');

            INSERT INTO request_notifications (request_id, user_id, type, message, actor_name, is_read, created_at)
            VALUES
              (1, 'user-1', 'status_changed', 'Moved to approved', 'Tooney', 0, '2026-04-02T00:00:00+00:00'),
              (1, 'user-1', 'comment', 'Admin left a comment', 'Tooney', 1, '2026-04-03T00:00:00+00:00'),
              (1, 'user-1', 'status_changed', 'Moved to fulfilled', 'Tooney', 0, '2026-04-04T00:00:00+00:00');
            """
        )

        app = FastAPI()
        app.include_router(notifications.router, prefix='/api/notifications')

        def override_db():
            yield self.conn

        async def override_user():
            return {'user_id': 'user-1', 'username': 'andrew'}

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        self.client = TestClient(app)
        self.app = app

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.conn.close()

    def test_summary_reports_unread_totals_and_unread_by_type(self):
        response = self.client.get('/api/notifications/summary')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], 3)
        self.assertEqual(body['unread'], 2)
        self.assertEqual(body['by_type']['status_changed'], 2)
        self.assertEqual(body['by_type']['comment'], 0)

    def test_mark_all_notifications_read_clears_summary(self):
        mark_response = self.client.post('/api/notifications/read-all')
        self.assertEqual(mark_response.status_code, 200)

        response = self.client.get('/api/notifications/summary')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['unread'], 0)
        self.assertEqual(body['by_type']['status_changed'], 0)


if __name__ == '__main__':
    unittest.main()
