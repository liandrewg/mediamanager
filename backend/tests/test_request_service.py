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


class DuplicateRequestConsolidationTests(unittest.TestCase):
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

            CREATE TABLE request_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT
            );

            CREATE TABLE user_roles (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL
            );
            """
        )

    def tearDown(self):
        self.conn.close()

    def create_request(
        self,
        user_id: str,
        username: str,
        tmdb_id: int,
        media_type: str,
        title: str,
        status: str,
        created_at: str,
        admin_note: str | None = None,
        poster_path: str | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO requests (user_id, username, tmdb_id, media_type, title, poster_path, status, admin_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, tmdb_id, media_type, title, poster_path, status, admin_note, created_at, created_at),
        )
        request_id = cursor.lastrowid
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (?, ?, ?, ?)",
            (request_id, user_id, username, created_at),
        )
        return request_id

    def add_supporter(self, request_id: int, user_id: str, username: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username, created_at) VALUES (?, ?, ?, ?)",
            (request_id, user_id, username, created_at),
        )

    def test_detects_duplicate_groups_by_normalized_title_and_tmdb(self):
        request_one = self.create_request(
            "user-1", "alice", 501, "movie", "Dune", "pending", "2026-03-10T10:00:00+00:00"
        )
        request_two = self.create_request(
            "user-2", "bob", 777, "movie", "  dune  ", "approved", "2026-03-09T10:00:00+00:00"
        )
        request_three = self.create_request(
            "user-3", "cara", 777, "movie", "Dune Part One", "pending", "2026-03-11T10:00:00+00:00"
        )
        self.add_supporter(request_one, "fan-1", "fan", "2026-03-12T10:00:00+00:00")

        self.create_request(
            "user-4", "dan", 777, "tv", "Dune", "pending", "2026-03-11T12:00:00+00:00"
        )
        self.create_request(
            "user-5", "erin", 777, "movie", "Dune", "fulfilled", "2026-03-08T10:00:00+00:00"
        )
        self.conn.commit()

        groups = request_service.get_duplicate_request_groups(self.conn)

        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["media_type"], "movie")
        self.assertEqual(group["normalized_title"], "dune")
        self.assertTrue(group["matched_by_title"])
        self.assertTrue(group["matched_by_tmdb"])
        self.assertEqual(group["shared_tmdb_ids"], [777])
        self.assertEqual(set(group["request_ids"]), {request_one, request_two, request_three})
        self.assertEqual(group["requests"][0]["id"], request_two)
        self.assertEqual(group["total_supporters"], 4)

    def test_merge_moves_supporters_preserves_target_and_notifies_impacted_users(self):
        target_request = self.create_request(
            "owner-1",
            "alice",
            1001,
            "movie",
            "Arrival",
            "pending",
            "2026-03-10T10:00:00+00:00",
        )
        source_request_a = self.create_request(
            "owner-2",
            "bob",
            1002,
            "movie",
            "  arrival ",
            "approved",
            "2026-03-05T10:00:00+00:00",
            admin_note="Prefer Blu-ray rip",
            poster_path="/arrival-a.jpg",
        )
        source_request_b = self.create_request(
            "owner-3",
            "cara",
            1002,
            "movie",
            "Arrival (2016)",
            "pending",
            "2026-03-08T10:00:00+00:00",
        )
        self.add_supporter(target_request, "shared-1", "sam", "2026-03-11T00:00:00+00:00")
        self.add_supporter(source_request_a, "shared-1", "sam", "2026-03-06T00:00:00+00:00")
        self.add_supporter(source_request_b, "fan-2", "max", "2026-03-09T00:00:00+00:00")
        self.conn.execute(
            "INSERT INTO user_roles (user_id, username, role) VALUES ('admin-1', 'Casey Admin', 'admin')"
        )
        self.conn.commit()

        result = request_service.merge_duplicate_requests(
            self.conn,
            target_request_id=target_request,
            source_request_ids=[source_request_b, source_request_a],
            changed_by="admin-1",
        )

        merged_target = result["target"]
        self.assertEqual(merged_target["id"], target_request)
        self.assertEqual(merged_target["status"], "pending")
        self.assertEqual(merged_target["created_at"], "2026-03-05T10:00:00+00:00")
        self.assertEqual(merged_target["poster_path"], "/arrival-a.jpg")
        self.assertEqual(merged_target["supporter_count"], 5)
        self.assertIn("Prefer Blu-ray rip", merged_target["admin_note"])
        self.assertIn("[DUPLICATE-MERGE]", merged_target["admin_note"])
        self.assertIn(f"#{source_request_a}", merged_target["admin_note"])
        self.assertIn(f"#{source_request_b}", merged_target["admin_note"])

        target_supporters = self.conn.execute(
            "SELECT user_id, created_at FROM request_supporters WHERE request_id = ? ORDER BY user_id",
            (target_request,),
        ).fetchall()
        self.assertEqual(
            {row["user_id"] for row in target_supporters},
            {"owner-1", "owner-2", "owner-3", "shared-1", "fan-2"},
        )
        shared_supporter = next(row for row in target_supporters if row["user_id"] == "shared-1")
        self.assertEqual(shared_supporter["created_at"], "2026-03-06T00:00:00+00:00")

        remaining_source_supporters = self.conn.execute(
            "SELECT COUNT(*) FROM request_supporters WHERE request_id IN (?, ?)",
            (source_request_a, source_request_b),
        ).fetchone()[0]
        self.assertEqual(remaining_source_supporters, 0)

        source_rows = self.conn.execute(
            "SELECT id, status, admin_note FROM requests WHERE id IN (?, ?) ORDER BY id",
            (source_request_a, source_request_b),
        ).fetchall()
        self.assertTrue(all(row["status"] == "denied" for row in source_rows))
        self.assertTrue(all(f"#{target_request}" in row["admin_note"] for row in source_rows))

        history_rows = self.conn.execute(
            "SELECT request_id, old_status, new_status, changed_by, note FROM request_history ORDER BY id"
        ).fetchall()
        self.assertEqual(len(history_rows), 3)
        self.assertEqual(history_rows[0]["request_id"], target_request)
        self.assertEqual(history_rows[0]["old_status"], "pending")
        self.assertEqual(history_rows[0]["new_status"], "pending")
        self.assertIn("[DUPLICATE-MERGE]", history_rows[0]["note"])
        self.assertEqual(history_rows[1]["new_status"], "denied")
        self.assertEqual(history_rows[2]["new_status"], "denied")

        comment_row = self.conn.execute(
            "SELECT user_id, username, is_admin, body FROM request_comments WHERE request_id = ?",
            (target_request,),
        ).fetchone()
        self.assertEqual(comment_row["user_id"], "system")
        self.assertEqual(comment_row["username"], "System")
        self.assertEqual(comment_row["is_admin"], 1)
        self.assertIn("[DUPLICATE-MERGE]", comment_row["body"])

        notification_rows = self.conn.execute(
            "SELECT request_id, user_id, type, actor_name, message FROM request_notifications ORDER BY user_id"
        ).fetchall()
        self.assertEqual(result["notifications_created"], 4)
        self.assertEqual(
            {row["user_id"] for row in notification_rows},
            {"owner-2", "owner-3", "shared-1", "fan-2"},
        )
        self.assertTrue(all(row["request_id"] == target_request for row in notification_rows))
        self.assertTrue(all(row["type"] == "request_merged" for row in notification_rows))
        self.assertTrue(all(row["actor_name"] == "Casey Admin" for row in notification_rows))
        self.assertTrue(all(f"#{target_request}" in row["message"] for row in notification_rows))

        self.assertEqual(request_service.get_duplicate_request_groups(self.conn), [])


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
