import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mediamanager.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = get_db_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL,
            tmdb_id     INTEGER NOT NULL,
            media_type  TEXT NOT NULL CHECK(media_type IN ('movie', 'tv', 'book')),
            title       TEXT NOT NULL,
            poster_path TEXT,
            status      TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending', 'approved', 'denied', 'fulfilled')),
            admin_note  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
        CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
        CREATE INDEX IF NOT EXISTS idx_requests_tmdb_id ON requests(tmdb_id);

        CREATE TABLE IF NOT EXISTS request_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id  INTEGER NOT NULL REFERENCES requests(id),
            old_status  TEXT NOT NULL,
            new_status  TEXT NOT NULL,
            changed_by  TEXT NOT NULL,
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS request_supporters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id  INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(request_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_request_supporters_request_id ON request_supporters(request_id);
        CREATE INDEX IF NOT EXISTS idx_request_supporters_user_id ON request_supporters(user_id);

        CREATE TABLE IF NOT EXISTS backlog (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL,
            type        TEXT NOT NULL DEFAULT 'bug'
                            CHECK(type IN ('bug', 'feature')),
            title       TEXT NOT NULL,
            description TEXT,
            status      TEXT NOT NULL DEFAULT 'reported'
                            CHECK(status IN ('reported', 'triaged', 'in_progress', 'ready_for_test', 'resolved', 'wont_fix')),
            priority    TEXT NOT NULL DEFAULT 'medium'
                            CHECK(priority IN ('low', 'medium', 'high', 'critical')),
            admin_note  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_backlog_status ON backlog(status);
        CREATE INDEX IF NOT EXISTS idx_backlog_type ON backlog(type);

        CREATE TABLE IF NOT EXISTS user_roles (
            user_id     TEXT PRIMARY KEY,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'user'
                            CHECK(role IN ('user', 'admin')),
            granted_by  TEXT,
            jellyfin_token TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sla_policy (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            target_days INTEGER NOT NULL DEFAULT 7 CHECK (target_days >= 1),
            warning_days INTEGER NOT NULL DEFAULT 2 CHECK (warning_days >= 0),
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Migration: add jellyfin_token column to user_roles if missing
    try:
        conn.execute("SELECT jellyfin_token FROM user_roles LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE user_roles ADD COLUMN jellyfin_token TEXT")
        conn.commit()

    # Migration: recreate backlog table if it lacks 'ready_for_test' status
    try:
        conn.execute("INSERT INTO backlog (user_id, username, title, status) VALUES ('__test__', '__test__', '__test__', 'ready_for_test')")
        conn.execute("DELETE FROM backlog WHERE user_id = '__test__'")
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.executescript("""
            ALTER TABLE backlog RENAME TO backlog_old;

            CREATE TABLE backlog (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                username    TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'bug'
                                CHECK(type IN ('bug', 'feature')),
                title       TEXT NOT NULL,
                description TEXT,
                status      TEXT NOT NULL DEFAULT 'reported'
                                CHECK(status IN ('reported', 'triaged', 'in_progress', 'ready_for_test', 'resolved', 'wont_fix')),
                priority    TEXT NOT NULL DEFAULT 'medium'
                                CHECK(priority IN ('low', 'medium', 'high', 'critical')),
                admin_note  TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO backlog (id, user_id, username, type, title, description, status, priority, admin_note, created_at, updated_at)
                SELECT id, user_id, username, type, title, description, status, priority, admin_note, created_at, updated_at
                FROM backlog_old;

            DROP TABLE backlog_old;

            CREATE INDEX IF NOT EXISTS idx_backlog_status ON backlog(status);
            CREATE INDEX IF NOT EXISTS idx_backlog_type ON backlog(type);
        """)

    # Migration: add 'book' to requests.media_type CHECK constraint
    try:
        conn.execute("INSERT INTO requests (user_id, username, tmdb_id, media_type, title) VALUES ('__test__', '__test__', 0, 'book', '__test__')")
        conn.execute("DELETE FROM requests WHERE user_id = '__test__'")
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.executescript("""
            PRAGMA foreign_keys=OFF;

            ALTER TABLE requests RENAME TO requests_old;

            CREATE TABLE requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                username    TEXT NOT NULL,
                tmdb_id     INTEGER NOT NULL,
                media_type  TEXT NOT NULL CHECK(media_type IN ('movie', 'tv', 'book')),
                title       TEXT NOT NULL,
                poster_path TEXT,
                status      TEXT NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending', 'approved', 'denied', 'fulfilled')),
                admin_note  TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO requests (id, user_id, username, tmdb_id, media_type, title, poster_path, status, admin_note, created_at, updated_at)
                SELECT id, user_id, username, tmdb_id, media_type, title, poster_path, status, admin_note, created_at, updated_at
                FROM requests_old;

            DROP TABLE requests_old;

            ALTER TABLE request_history RENAME TO request_history_old;

            CREATE TABLE request_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id  INTEGER NOT NULL REFERENCES requests(id),
                old_status  TEXT NOT NULL,
                new_status  TEXT NOT NULL,
                changed_by  TEXT NOT NULL,
                note        TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO request_history SELECT * FROM request_history_old;

            DROP TABLE request_history_old;

            CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
            CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
            CREATE INDEX IF NOT EXISTS idx_requests_tmdb_id ON requests(tmdb_id);

            PRAGMA foreign_keys=ON;
        """)

    # Migration: fix request_history FK if it was broken by the books migration
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name='request_history'").fetchone()
    if row and 'requests_old' in row[0]:
        conn.executescript("""
            PRAGMA foreign_keys=OFF;

            ALTER TABLE request_history RENAME TO request_history_old;

            CREATE TABLE request_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id  INTEGER NOT NULL REFERENCES requests(id),
                old_status  TEXT NOT NULL,
                new_status  TEXT NOT NULL,
                changed_by  TEXT NOT NULL,
                note        TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO request_history SELECT * FROM request_history_old;

            DROP TABLE request_history_old;

            PRAGMA foreign_keys=ON;
        """)

    # Migration: ensure request_supporters exists in older DBs and backfill owners.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS request_supporters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id  INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(request_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_request_supporters_request_id ON request_supporters(request_id);
        CREATE INDEX IF NOT EXISTS idx_request_supporters_user_id ON request_supporters(user_id);
    """)
    conn.execute(
        """
        INSERT OR IGNORE INTO request_supporters (request_id, user_id, username, created_at)
        SELECT id, user_id, username, created_at FROM requests
        """
    )
    conn.commit()

    # Migration: add jellyfin_item_id to requests table
    try:
        conn.execute("SELECT jellyfin_item_id FROM requests LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE requests ADD COLUMN jellyfin_item_id TEXT")
        conn.execute(
        """
        INSERT OR IGNORE INTO sla_policy (id, target_days, warning_days)
        VALUES (1, ?, ?)
        """,
        (7, 2),
    )
    conn.execute(
        """
        UPDATE sla_policy
        SET warning_days = CASE
            WHEN warning_days < 0 THEN 0
            WHEN warning_days >= target_days THEN target_days - 1
            ELSE warning_days
        END
        WHERE id = 1
        """
    )
    conn.commit()

    # Migration: add request_comments table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS request_comments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id  INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
            user_id     TEXT NOT NULL,
            username    TEXT NOT NULL,
            is_admin    INTEGER NOT NULL DEFAULT 0,
            body        TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_request_comments_request_id ON request_comments(request_id);

        CREATE TABLE IF NOT EXISTS request_notifications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id    INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
            user_id       TEXT NOT NULL,
            type          TEXT NOT NULL,
            message       TEXT NOT NULL,
            actor_user_id TEXT,
            actor_name    TEXT,
            is_read       INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_request_notifications_user_id ON request_notifications(user_id);
        CREATE INDEX IF NOT EXISTS idx_request_notifications_request_id ON request_notifications(request_id);
        CREATE INDEX IF NOT EXISTS idx_request_notifications_is_read ON request_notifications(is_read);

        CREATE TABLE IF NOT EXISTS request_blockers (
            request_id   INTEGER PRIMARY KEY REFERENCES requests(id) ON DELETE CASCADE,
            reason       TEXT NOT NULL,
            note         TEXT,
            review_on    TEXT NOT NULL,
            updated_by   TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_request_blockers_review_on ON request_blockers(review_on);
    """)
    conn.commit()

    conn.close()
