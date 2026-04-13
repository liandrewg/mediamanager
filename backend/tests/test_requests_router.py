import sqlite3
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.routers import requests


class RequestTimelineRouteTests(unittest.TestCase):
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
                status TEXT NOT NULL DEFAULT 'pending',
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

            CREATE TABLE user_roles (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL
            );
            """
        )
        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('owner-1', 'Alice', 101, 'movie', 'Arrival', 'approved', '2026-04-10T10:00:00+00:00', '2026-04-10T10:00:00+00:00')
            """
        )
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (1, 'owner-1', 'Alice', '2026-04-10T10:00:00+00:00')"
        )
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (1, 'fan-2', 'Bob', '2026-04-10T12:00:00+00:00')"
        )
        self.conn.execute(
            "INSERT INTO user_roles (user_id, username, role) VALUES ('admin-1', 'Casey Admin', 'admin')"
        )
        self.conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note, created_at)
            VALUES (1, 'pending', 'approved', 'admin-1', 'Approved for the next import batch', '2026-04-11T09:00:00+00:00')
            """
        )
        self.conn.commit()

        self.app = FastAPI()
        self.app.include_router(requests.router, prefix='/api/requests')

        def override_db():
            yield self.conn

        async def override_user():
            return {'user_id': 'fan-2', 'username': 'Bob', 'is_admin': False}

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = override_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.conn.close()

    def test_supporter_can_view_request_timeline(self):
        response = self.client.get('/api/requests/1/timeline')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 3)
        self.assertEqual(body[0]['event_type'], 'request_submitted')
        self.assertEqual(body[1]['event_type'], 'supporter_joined')
        self.assertEqual(body[2]['event_type'], 'status_changed')

    def test_non_supporter_is_denied(self):
        async def override_other_user():
            return {'user_id': 'outsider', 'username': 'Eve', 'is_admin': False}

        self.app.dependency_overrides[get_current_user] = override_other_user
        response = self.client.get('/api/requests/1/timeline')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'Access denied')


if __name__ == '__main__':
    unittest.main()
