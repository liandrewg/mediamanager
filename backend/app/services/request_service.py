import sqlite3
import math
from datetime import datetime


def create_request(
    conn: sqlite3.Connection,
    user_id: str,
    username: str,
    tmdb_id: int,
    media_type: str,
    title: str,
    poster_path: str | None,
) -> dict:
    # Check for duplicate
    existing = conn.execute(
        "SELECT id, status FROM requests WHERE tmdb_id = ? AND media_type = ? AND user_id = ? AND status != 'denied'",
        (tmdb_id, media_type, user_id),
    ).fetchone()
    if existing:
        raise ValueError(f"You already have a {existing['status']} request for this title")

    cursor = conn.execute(
        """INSERT INTO requests (user_id, username, tmdb_id, media_type, title, poster_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, tmdb_id, media_type, title, poster_path),
    )
    conn.commit()
    return get_request_by_id(conn, cursor.lastrowid)


def get_request_by_id(conn: sqlite3.Connection, request_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if row:
        return dict(row)
    return None


def get_user_requests(
    conn: sqlite3.Connection,
    user_id: str,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    where = "WHERE user_id = ?"
    params: list = [user_id]
    if status:
        where += " AND status = ?"
        params.append(status)

    total = conn.execute(f"SELECT COUNT(*) FROM requests {where}", params).fetchone()[0]
    offset = (page - 1) * limit
    rows = conn.execute(
        f"SELECT * FROM requests {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
    }


def get_all_requests(
    conn: sqlite3.Connection,
    status: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    where_parts = []
    params: list = []
    if status:
        where_parts.append("status = ?")
        params.append(status)
    if user_id:
        where_parts.append("user_id = ?")
        params.append(user_id)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    total = conn.execute(f"SELECT COUNT(*) FROM requests {where}", params).fetchone()[0]
    offset = (page - 1) * limit
    rows = conn.execute(
        f"SELECT * FROM requests {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
    }


def update_request_status(
    conn: sqlite3.Connection,
    request_id: int,
    new_status: str,
    changed_by: str,
    admin_note: str | None = None,
) -> dict:
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        raise ValueError("Request not found")

    old_status = row["status"]
    now = datetime.utcnow().isoformat()

    conn.execute(
        "UPDATE requests SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
        (new_status, admin_note, now, request_id),
    )
    conn.execute(
        """INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
           VALUES (?, ?, ?, ?, ?)""",
        (request_id, old_status, new_status, changed_by, admin_note),
    )
    conn.commit()
    return get_request_by_id(conn, request_id)


def delete_request(conn: sqlite3.Connection, request_id: int, user_id: str) -> bool:
    row = conn.execute(
        "SELECT * FROM requests WHERE id = ? AND user_id = ?", (request_id, user_id)
    ).fetchone()
    if not row:
        raise ValueError("Request not found")
    if row["status"] != "pending":
        raise ValueError("Can only cancel pending requests")
    conn.execute("DELETE FROM requests WHERE id = ?", (request_id,))
    conn.commit()
    return True


def get_request_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM requests GROUP BY status"
    ).fetchall()
    stats = {r["status"]: r["count"] for r in rows}
    total = sum(stats.values())
    unique_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM requests"
    ).fetchone()[0]
    return {
        "total": total,
        "pending": stats.get("pending", 0),
        "approved": stats.get("approved", 0),
        "denied": stats.get("denied", 0),
        "fulfilled": stats.get("fulfilled", 0),
        "unique_users": unique_users,
    }


def get_open_requests(conn: sqlite3.Connection) -> list[dict]:
    """Get all pending or approved requests (candidates for auto-fulfillment)."""
    rows = conn.execute(
        "SELECT * FROM requests WHERE status IN ('pending', 'approved')"
    ).fetchall()
    return [dict(r) for r in rows]


def auto_fulfill_request(conn: sqlite3.Connection, request_id: int) -> None:
    """Mark a request as fulfilled by the system."""
    now = datetime.utcnow().isoformat()
    row = conn.execute("SELECT status FROM requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        return
    old_status = row["status"]
    conn.execute(
        "UPDATE requests SET status = 'fulfilled', admin_note = 'Auto-fulfilled: found in library', updated_at = ? WHERE id = ?",
        (now, request_id),
    )
    conn.execute(
        """INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
           VALUES (?, ?, 'fulfilled', 'system', 'Auto-fulfilled: found in Jellyfin library')""",
        (request_id, old_status),
    )
    conn.commit()


def get_request_for_tmdb(
    conn: sqlite3.Connection, tmdb_id: int, media_type: str, user_id: str
) -> str | None:
    row = conn.execute(
        "SELECT status FROM requests WHERE tmdb_id = ? AND media_type = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1",
        (tmdb_id, media_type, user_id),
    ).fetchone()
    return row["status"] if row else None
