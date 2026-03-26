import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

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
            ("u1", "alice", 101, "movie", "Interstellar", "pending", None, "2026-03-10T10:00:00+00:00"),
            ("u2", "bob", 202, "tv", "Severance", "approved", None, "2026-03-11T10:00:00+00:00"),
            ("u3", "cara", 303, "book", "Dune", "pending", None, "2026-03-12T10:00:00+00:00"),
            (
                "u5",
                "erin",
                404,
                "movie",
                "Old Denial",
                "denied",
                "[AUTO-CLOSED-DENIED] stale denial closed",
                "2026-03-01T10:00:00+00:00",
            ),
        ]
        for user_id, username, tmdb_id, media_type, title, status, admin_note, created_at in rows:
            cur = self.conn.execute(
                """
                INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, admin_note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, tmdb_id, media_type, title, status, admin_note, created_at, created_at),
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

    def test_hides_auto_closed_denied_by_default(self):
        result = request_service.get_all_requests(self.conn, sort="newest", page=1, limit=20)

        titles = [item["title"] for item in result["items"]]
        self.assertNotIn("Old Denial", titles)
        self.assertEqual(result["total"], 3)

    def test_can_include_auto_closed_denied_items(self):
        result = request_service.get_all_requests(
            self.conn,
            status="denied",
            include_auto_closed_denied=True,
            sort="newest",
            page=1,
            limit=20,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["title"], "Old Denial")


class BulkStatusUpdateTests(unittest.TestCase):
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
            """
        )

        rows = [
            ("u1", "alice", 101, "movie", "Interstellar", "pending", "2026-03-10T10:00:00+00:00"),
            ("u2", "bob", 202, "tv", "Severance", "approved", "2026-03-11T10:00:00+00:00"),
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
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_bulk_update_changes_multiple_requests_and_tracks_history(self):
        result = request_service.bulk_update_request_status(
            self.conn,
            request_ids=[1, 2],
            new_status="denied",
            changed_by="admin-1",
            admin_note="Not available yet",
        )

        self.assertEqual(result["missing"], [])
        self.assertEqual(len(result["updated"]), 2)
        self.assertTrue(all(item["status"] == "denied" for item in result["updated"]))

        history_rows = self.conn.execute(
            "SELECT request_id, old_status, new_status, changed_by, note FROM request_history ORDER BY request_id"
        ).fetchall()
        self.assertEqual(len(history_rows), 2)
        self.assertEqual(history_rows[0]["request_id"], 1)
        self.assertEqual(history_rows[0]["old_status"], "pending")
        self.assertEqual(history_rows[0]["new_status"], "denied")
        self.assertEqual(history_rows[0]["changed_by"], "admin-1")
        self.assertEqual(history_rows[0]["note"], "Not available yet")
        self.assertEqual(history_rows[1]["request_id"], 2)
        self.assertEqual(history_rows[1]["old_status"], "approved")

    def test_bulk_update_reports_missing_ids(self):
        result = request_service.bulk_update_request_status(
            self.conn,
            request_ids=[2, 999],
            new_status="fulfilled",
            changed_by="admin-2",
        )

        self.assertEqual(result["missing"], [999])
        self.assertEqual(len(result["updated"]), 1)
        self.assertEqual(result["updated"][0]["id"], 2)
        self.assertEqual(result["updated"][0]["status"], "fulfilled")


class RequestStatsAgingTests(unittest.TestCase):
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
            ("u1", "alice", 111, "movie", "Old Pending", "pending", "2026-03-01T00:00:00+00:00"),
            ("u2", "bob", 222, "tv", "Week Old Approved", "approved", "2026-03-08T00:00:00+00:00"),
            ("u3", "cara", 333, "book", "Fresh Pending", "pending", "2026-03-14T12:00:00+00:00"),
            ("u4", "dave", 444, "movie", "Already Fulfilled", "fulfilled", "2026-02-20T00:00:00+00:00"),
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

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_includes_open_request_aging_metrics(self):
        frozen_now = datetime(2026, 3, 16, 0, 0, tzinfo=timezone.utc)

        with patch.object(request_service, "datetime") as mock_datetime:
            mock_datetime.now.return_value = frozen_now
            mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
            mock_datetime.strptime.side_effect = datetime.strptime

            stats = request_service.get_request_stats(self.conn)

        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["fulfilled"], 1)
        self.assertEqual(stats["open_over_3_days"], 2)
        self.assertEqual(stats["open_over_7_days"], 2)
        self.assertEqual(stats["open_over_14_days"], 1)
        self.assertEqual(stats["oldest_open_days"], 15)
        self.assertEqual(stats["escalated_open"], 0)
        self.assertEqual(stats["closed_denied"], 0)


class HighDemandEscalationTests(unittest.TestCase):
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

            CREATE TABLE request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                note TEXT,
                created_at TEXT
            );
            """
        )

        # stale + high demand -> should escalate
        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u1', 'alice', 101, 'movie', 'The Big Ask', 'pending', '2026-03-01T00:00:00+00:00', '2026-03-01T00:00:00+00:00')
            """
        )
        for idx in range(1, 4):
            self.conn.execute(
                "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (1, ?, ?, '2026-03-01T00:00:00+00:00')",
                (f"s{idx}", f"supporter{idx}"),
            )

        # not stale enough -> should not escalate
        self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, created_at, updated_at)
            VALUES ('u2', 'bob', 202, 'tv', 'Fresh Demand', 'pending', '2026-03-15T00:00:00+00:00', '2026-03-15T00:00:00+00:00')
            """
        )
        for idx in range(1, 5):
            self.conn.execute(
                "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (2, ?, ?, '2026-03-15T00:00:00+00:00')",
                (f"f{idx}", f"fan{idx}"),
            )

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_escalates_stale_high_demand_requests_once(self):
        frozen_now = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)

        first = request_service.run_high_demand_escalation(self.conn, now=frozen_now)
        second = request_service.run_high_demand_escalation(self.conn, now=frozen_now)

        self.assertEqual(first["escalated"], 1)
        self.assertEqual(second["escalated"], 0)

        row = self.conn.execute("SELECT admin_note FROM requests WHERE id = 1").fetchone()
        self.assertIn("[AUTO-ESCALATED]", row["admin_note"])

        untouched = self.conn.execute("SELECT admin_note FROM requests WHERE id = 2").fetchone()
        self.assertIsNone(untouched["admin_note"])

        history_rows = self.conn.execute(
            "SELECT request_id, old_status, new_status, changed_by, note FROM request_history ORDER BY id"
        ).fetchall()
        self.assertEqual(len(history_rows), 1)
        self.assertEqual(history_rows[0]["request_id"], 1)
        self.assertEqual(history_rows[0]["old_status"], "pending")
        self.assertEqual(history_rows[0]["new_status"], "pending")
        self.assertEqual(history_rows[0]["changed_by"], "system")
        self.assertIn("[AUTO-ESCALATED]", history_rows[0]["note"])


class RequestNotificationTests(unittest.TestCase):
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
            VALUES ('owner-1', 'owner', 101, 'movie', 'Interstellar', 'pending', '2026-03-10T10:00:00+00:00', '2026-03-10T10:00:00+00:00')
            """
        )
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (1, 'owner-1', 'owner', '2026-03-10T10:00:00+00:00')"
        )
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (1, 'fan-2', 'fan', '2026-03-10T10:00:00+00:00')"
        )
        self.conn.execute(
            "INSERT INTO user_roles (user_id, username, role) VALUES ('admin-1', 'Casey Admin', 'admin')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_status_change_creates_notifications_for_all_supporters(self):
        request_service.update_request_status(
            self.conn,
            request_id=1,
            new_status="approved",
            changed_by="admin-1",
            admin_note="Looks good",
        )

        rows = self.conn.execute(
            "SELECT user_id, type, message, actor_name FROM request_notifications ORDER BY user_id"
        ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["user_id"], "fan-2")
        self.assertEqual(rows[1]["user_id"], "owner-1")
        self.assertTrue(all(r["type"] == "status_changed" for r in rows))
        self.assertTrue(all("pending to approved" in r["message"] for r in rows))
        self.assertTrue(all(r["actor_name"] == "Casey Admin" for r in rows))


class LifecycleRuleAutomationTests(unittest.TestCase):
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

            CREATE TABLE request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                note TEXT,
                created_at TEXT
            );
            """
        )

        fixtures = [
            ("u1", "alice", 500, "movie", "Stale Pending", "pending", None, "2026-03-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00"),
            ("u2", "bob", 600, "movie", "Stale Denied", "denied", "Manual denial note", "2026-02-20T00:00:00+00:00", "2026-03-01T00:00:00+00:00"),
        ]
        for row in fixtures:
            self.conn.execute(
                """
                INSERT INTO requests (user_id, username, tmdb_id, media_type, title, status, admin_note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_unified_lifecycle_rules_apply_once(self):
        frozen_now = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)

        first = request_service.run_request_lifecycle_rules(self.conn, now=frozen_now)
        second = request_service.run_request_lifecycle_rules(self.conn, now=frozen_now)

        self.assertEqual(first["reminded"], 1)
        self.assertEqual(first["auto_closed_denied"], 1)
        self.assertEqual(second["reminded"], 0)
        self.assertEqual(second["auto_closed_denied"], 0)

        pending = self.conn.execute("SELECT admin_note FROM requests WHERE title = 'Stale Pending'").fetchone()
        self.assertIn("[AUTO-PENDING-REMINDER]", pending["admin_note"])

        denied = self.conn.execute("SELECT admin_note FROM requests WHERE title = 'Stale Denied'").fetchone()
        self.assertIn("[AUTO-CLOSED-DENIED]", denied["admin_note"])

        stats = request_service.get_request_stats(self.conn)
        self.assertEqual(stats["closed_denied"], 1)


if __name__ == "__main__":
    unittest.main()
