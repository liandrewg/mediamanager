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
            media_type  TEXT NOT NULL CHECK(media_type IN ('movie', 'tv')),
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
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Migration: recreate backlog table if it lacks 'ready_for_test' status
    try:
        conn.execute("INSERT INTO backlog (user_id, username, title, status) VALUES ('__test__', '__test__', '__test__', 'ready_for_test')")
        conn.execute("DELETE FROM backlog WHERE user_id = '__test__'")
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        # Need to recreate table with updated CHECK constraint
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

    conn.close()
