import sqlite3
import math
from datetime import datetime, timezone

from app.config import settings


OPEN_REQUEST_STATUSES = ("pending", "approved")


def _serialize_request(conn: sqlite3.Connection, row: sqlite3.Row, user_id: str | None = None) -> dict:
    req = dict(row)

    supporters = conn.execute(
        "SELECT username FROM request_supporters WHERE request_id = ? ORDER BY created_at ASC",
        (req["id"],),
    ).fetchall()
    supporter_names = [r["username"] for r in supporters]
    req["supporters"] = supporter_names
    req["supporter_count"] = len(supporter_names)

    created_raw = req.get("created_at")
    created_dt = None
    if isinstance(created_raw, str):
        for parser in (datetime.fromisoformat, lambda value: datetime.strptime(value, "%Y-%m-%d %H:%M:%S")):
            try:
                created_dt = parser(created_raw)
                break
            except ValueError:
                continue
    if created_dt is None:
        created_dt = datetime.now(timezone.utc)
    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)

    days_open = max((datetime.now(timezone.utc) - created_dt).days, 0)
    req["days_open"] = days_open
    req["priority_score"] = round((req["supporter_count"] * 3) + min(days_open, 30), 1)

    req["is_owner"] = user_id == req["user_id"] if user_id else False
    req["user_supporting"] = False
    if user_id:
        req["user_supporting"] = bool(
            conn.execute(
                "SELECT 1 FROM request_supporters WHERE request_id = ? AND user_id = ?",
                (req["id"], user_id),
            ).fetchone()
        )
    # Generate watch URL if jellyfin_item_id is set
    jellyfin_item_id = req.get("jellyfin_item_id")
    if jellyfin_item_id:
        base = settings.jellyfin_url.rstrip("/")
        req["watch_url"] = f"{base}/web/index.html#!/details?id={jellyfin_item_id}"
    else:
        req["watch_url"] = None
    return req


def create_request(
    conn: sqlite3.Connection,
    user_id: str,
    username: str,
    tmdb_id: int,
    media_type: str,
    title: str,
    poster_path: str | None,
) -> dict:
    # If this user already supports an active request for this title, block duplicates.
    already_supporting = conn.execute(
        """
        SELECT r.id, r.status
        FROM requests r
        JOIN request_supporters s ON s.request_id = r.id
        WHERE r.tmdb_id = ?
          AND r.media_type = ?
          AND s.user_id = ?
          AND r.status IN ('pending', 'approved')
        LIMIT 1
        """,
        (tmdb_id, media_type, user_id),
    ).fetchone()
    if already_supporting:
        raise ValueError(f"You already support a {already_supporting['status']} request for this title")

    # Reuse active request for same title/media to create a community queue.
    existing_open = conn.execute(
        """
        SELECT * FROM requests
        WHERE tmdb_id = ?
          AND media_type = ?
          AND status IN ('pending', 'approved')
        ORDER BY CASE status WHEN 'approved' THEN 0 ELSE 1 END, created_at ASC
        LIMIT 1
        """,
        (tmdb_id, media_type),
    ).fetchone()

    if existing_open:
        conn.execute(
            "INSERT INTO request_supporters (request_id, user_id, username) VALUES (?, ?, ?)",
            (existing_open["id"], user_id, username),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM requests WHERE id = ?", (existing_open["id"],)).fetchone()
        return _serialize_request(conn, refreshed, user_id)

    cursor = conn.execute(
        """INSERT INTO requests (user_id, username, tmdb_id, media_type, title, poster_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, tmdb_id, media_type, title, poster_path),
    )
    request_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO request_supporters (request_id, user_id, username) VALUES (?, ?, ?)",
        (request_id, user_id, username),
    )
    conn.commit()
    return get_request_by_id(conn, request_id, user_id)


def get_request_by_id(conn: sqlite3.Connection, request_id: int, user_id: str | None = None) -> dict | None:
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if row:
        return _serialize_request(conn, row, user_id)
    return None


def get_user_requests(
    conn: sqlite3.Connection,
    user_id: str,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    where = "WHERE s.user_id = ?"
    params: list = [user_id]
    if status:
        where += " AND r.status = ?"
        params.append(status)

    total = conn.execute(
        f"SELECT COUNT(*) FROM requests r JOIN request_supporters s ON s.request_id = r.id {where}",
        params,
    ).fetchone()[0]
    offset = (page - 1) * limit
    rows = conn.execute(
        f"""
        SELECT r.*
        FROM requests r
        JOIN request_supporters s ON s.request_id = r.id
        {where}
        ORDER BY r.created_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    return {
        "items": [_serialize_request(conn, r, user_id) for r in rows],
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
    sort: str = "priority",
) -> dict:
    where_parts = []
    params: list = []
    if status:
        where_parts.append("r.status = ?")
        params.append(status)
    if user_id:
        where_parts.append("r.user_id = ?")
        params.append(user_id)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    total = conn.execute(f"SELECT COUNT(*) FROM requests r {where}", params).fetchone()[0]
    offset = (page - 1) * limit
    sort_sql = {
        "newest": "r.created_at DESC",
        "oldest": "r.created_at ASC",
        "supporters": "supporter_count DESC, r.created_at ASC",
        "priority": "supporter_count DESC, r.created_at ASC",
    }.get(sort, "supporter_count DESC, r.created_at ASC")

    rows = conn.execute(
        f"""
        SELECT r.*,
               (SELECT COUNT(*) FROM request_supporters s WHERE s.request_id = r.id) as supporter_count
        FROM requests r
        {where}
        ORDER BY {sort_sql}
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    return {
        "items": [_serialize_request(conn, r, user_id) for r in rows],
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
    jellyfin_item_id: str | None = None,
) -> dict:
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        raise ValueError("Request not found")

    old_status = row["status"]
    now = datetime.utcnow().isoformat()

    if jellyfin_item_id is not None:
        conn.execute(
            "UPDATE requests SET status = ?, admin_note = ?, jellyfin_item_id = ?, updated_at = ? WHERE id = ?",
            (new_status, admin_note, jellyfin_item_id, now, request_id),
        )
    else:
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
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        raise ValueError("Request not found")
    if row["status"] != "pending":
        raise ValueError("Can only cancel pending requests")

    supporter = conn.execute(
        "SELECT * FROM request_supporters WHERE request_id = ? AND user_id = ?",
        (request_id, user_id),
    ).fetchone()
    if not supporter:
        raise ValueError("You are not supporting this request")

    conn.execute(
        "DELETE FROM request_supporters WHERE request_id = ? AND user_id = ?",
        (request_id, user_id),
    )

    if row["user_id"] == user_id:
        next_owner = conn.execute(
            """
            SELECT user_id, username
            FROM request_supporters
            WHERE request_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()
        if next_owner:
            conn.execute(
                "UPDATE requests SET user_id = ?, username = ?, updated_at = ? WHERE id = ?",
                (next_owner["user_id"], next_owner["username"], datetime.utcnow().isoformat(), request_id),
            )
        else:
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
        "SELECT COUNT(DISTINCT user_id) FROM request_supporters"
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
        """
        SELECT r.status
        FROM requests r
        JOIN request_supporters s ON s.request_id = r.id
        WHERE r.tmdb_id = ?
          AND r.media_type = ?
          AND s.user_id = ?
          AND r.status IN ('pending', 'approved')
        ORDER BY r.created_at DESC
        LIMIT 1
        """,
        (tmdb_id, media_type, user_id),
    ).fetchone()
    return row["status"] if row else None


def get_community_request(
    conn: sqlite3.Connection,
    tmdb_id: int,
    media_type: str,
    user_id: str,
) -> dict | None:
    row = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE tmdb_id = ?
          AND media_type = ?
          AND status IN ('pending', 'approved')
        ORDER BY CASE status WHEN 'approved' THEN 0 ELSE 1 END, created_at ASC
        LIMIT 1
        """,
        (tmdb_id, media_type),
    ).fetchone()
    if not row:
        return None
    return _serialize_request(conn, row, user_id)
