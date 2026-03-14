import sqlite3
import unittest

from app.services import request_service


class GetAllRequestsFilteringTests(unittest.TestCase):
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
                poster_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE request_supporters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(request_id, user_id)
            );
            """
        )

        rows = [
            ("u1", "alice", 101, "movie", "Interstellar", "pending", "2026-03-10T10:00:00+00:00"),
            ("u2", "bob", 202, "tv", "Severance", "approved", "2026-03-11T10:00:00+00:00"),
            ("u3", "cara", 303, "book", "Dune", "pending", "2026-03-12T10:00:00+00:00"),
        ]
        for user_id, username, tmdb_id, media_type, title, status, created_at in rows:
            cur = self.conn.execute(
                """
                INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, tmdb_id, media_type, title, status, created_at, created_at),
            )
            req_id = cur.lastrowid
            self.conn.execute(
                "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (?, ?, ?, ?)",
                (req_id, user_id, username, created_at),
            )

        # extra supporter on movie item to ensure sorting still works with filtering
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (1, 'u4', 'dave', '2026-03-13T10:00:00+00:00')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_filters_by_media_type(self):
        result = request_service.get_all_requests(
            self.conn,
            media_type="book",
            sort="priority",
            page=1,
            limit=20,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "Dune")
        self.assertEqual(result["items"][0]["media_type"], "book")

    def test_combines_status_and_media_type_filters(self):
        result = request_service.get_all_requests(
            self.conn,
            status="pending",
            media_type="movie",
            sort="priority",
            page=1,
            limit=20,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["title"], "Interstellar")


if __name__ == "__main__":
    unittest.main()
