import sqlite3
import math
from datetime import datetime, timezone

from app.config import settings


OPEN_REQUEST_STATUSES = ("pending", "approved")
ESCALATION_MIN_SUPPORTERS = 3
ESCALATION_MIN_AGE_DAYS = 10
ESCALATION_MARKER = "[AUTO-ESCALATED]"

PENDING_REMINDER_MIN_AGE_DAYS = 3
PENDING_REMINDER_MARKER = "[AUTO-PENDING-REMINDER]"
DENIED_AUTO_CLOSE_MIN_AGE_DAYS = 14
DENIED_AUTO_CLOSE_MARKER = "[AUTO-CLOSED-DENIED]"


def _parse_request_datetime(value: str | None) -> datetime:
    if isinstance(value, str):
        for parser in (datetime.fromisoformat, lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")):
            try:
                parsed = parser(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
    return datetime.now(timezone.utc)


def _serialize_request(conn: sqlite3.Connection, row: sqlite3.Row, user_id: str | None = None) -> dict:
    req = dict(row)

    supporters = conn.execute(
        "SELECT username FROM request_supporters WHERE request_id = ? ORDER BY created_at ASC",
        (req["id"],),
    ).fetchall()
    supporter_names = [r["username"] for r in supporters]
    req["supporters"] = supporter_names
    req["supporter_count"] = len(supporter_names)

    created_dt = _parse_request_datetime(req.get("created_at"))
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


def _create_request_notifications(
    conn: sqlite3.Connection,
    request_id: int,
    event_type: str,
    message: str,
    actor_user_id: str | None = None,
    actor_name: str | None = None,
    exclude_user_id: str | None = None,
) -> None:
    try:
        recipients = conn.execute(
            "SELECT DISTINCT user_id FROM request_supporters WHERE request_id = ?",
            (request_id,),
        ).fetchall()

        for recipient in recipients:
            recipient_user_id = recipient["user_id"]
            if exclude_user_id and recipient_user_id == exclude_user_id:
                continue
            conn.execute(
                """
                INSERT INTO request_notifications (request_id, user_id, type, message, actor_user_id, actor_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, recipient_user_id, event_type, message, actor_user_id, actor_name),
            )
    except sqlite3.OperationalError:
        # Notification table may be absent in isolated unit tests using partial schemas.
        return


def _resolve_actor_name(conn: sqlite3.Connection, user_id: str) -> str:
    try:
        actor_name = conn.execute(
            "SELECT username FROM user_roles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if actor_name:
            return actor_name["username"]
    except sqlite3.OperationalError:
        pass
    return "Admin"


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
        _create_request_notifications(
            conn,
            existing_open["id"],
            event_type="new_supporter",
            message=f"{username} also requested this title.",
            actor_user_id=user_id,
            actor_name=username,
            exclude_user_id=user_id,
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
    media_type: str | None = None,
    page: int = 1,
    limit: int = 20,
    sort: str = "priority",
    include_auto_closed_denied: bool = False,
) -> dict:
    where_parts = []
    params: list = []
    if status:
        where_parts.append("r.status = ?")
        params.append(status)
    if user_id:
        where_parts.append("r.user_id = ?")
        params.append(user_id)
    if media_type:
        where_parts.append("r.media_type = ?")
        params.append(media_type)
    if not include_auto_closed_denied:
        where_parts.append("NOT (r.status = 'denied' AND r.admin_note LIKE ?)")
        params.append(f"%{DENIED_AUTO_CLOSE_MARKER}%")

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
    if old_status != new_status:
        display_actor_name = _resolve_actor_name(conn, changed_by)
        _create_request_notifications(
            conn,
            request_id,
            event_type="status_changed",
            message=f"Request moved from {old_status} to {new_status}.",
            actor_user_id=changed_by,
            actor_name=display_actor_name,
        )
    conn.commit()
    return get_request_by_id(conn, request_id)


def bulk_update_request_status(
    conn: sqlite3.Connection,
    request_ids: list[int],
    new_status: str,
    changed_by: str,
    admin_note: str | None = None,
) -> dict:
    """Bulk update request statuses and write request_history entries for each change."""
    if not request_ids:
        return {"updated": [], "missing": []}

    updated: list[dict] = []
    missing: list[int] = []
    now = datetime.utcnow().isoformat()

    for request_id in request_ids:
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            missing.append(request_id)
            continue

        old_status = row["status"]
        conn.execute(
            "UPDATE requests SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
            (new_status, admin_note, now, request_id),
        )
        conn.execute(
            """INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
               VALUES (?, ?, ?, ?, ?)""",
            (request_id, old_status, new_status, changed_by, admin_note),
        )
        if old_status != new_status:
            display_actor_name = _resolve_actor_name(conn, changed_by)
            _create_request_notifications(
                conn,
                request_id,
                event_type="status_changed",
                message=f"Request moved from {old_status} to {new_status}.",
                actor_user_id=changed_by,
                actor_name=display_actor_name,
            )
        updated.append(get_request_by_id(conn, request_id))

    conn.commit()
    return {"updated": updated, "missing": missing}


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


def run_high_demand_escalation(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    min_supporters: int = ESCALATION_MIN_SUPPORTERS,
    min_age_days: int = ESCALATION_MIN_AGE_DAYS,
) -> dict:
    """Escalate old, high-demand open requests by tagging them for admin attention."""
    now = now or datetime.now(timezone.utc)
    escalated = 0

    rows = conn.execute(
        """
        SELECT r.*, (SELECT COUNT(*) FROM request_supporters s WHERE s.request_id = r.id) as supporter_count
        FROM requests r
        WHERE r.status IN ('pending', 'approved')
        """
    ).fetchall()

    for row in rows:
        req = dict(row)
        created_dt = _parse_request_datetime(req.get("created_at"))
        age_days = max((now - created_dt).days, 0)

        if req["supporter_count"] < min_supporters or age_days < min_age_days:
            continue

        existing_note = req.get("admin_note") or ""
        if ESCALATION_MARKER in existing_note:
            continue

        escalation_note = (
            f"{ESCALATION_MARKER} High-demand request has been open {age_days} days "
            f"with {req['supporter_count']} supporters."
        )
        merged_note = f"{existing_note}\n\n{escalation_note}".strip() if existing_note else escalation_note

        conn.execute(
            "UPDATE requests SET admin_note = ?, updated_at = ? WHERE id = ?",
            (merged_note, now.isoformat(), req["id"]),
        )
        conn.execute(
            """INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
               VALUES (?, ?, ?, 'system', ?)""",
            (req["id"], req["status"], req["status"], escalation_note),
        )
        escalated += 1

    conn.commit()
    return {"escalated": escalated}


def run_pending_approval_reminders(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    min_age_days: int = PENDING_REMINDER_MIN_AGE_DAYS,
) -> dict:
    """Add an admin-visible note/history reminder for stale pending requests."""
    now = now or datetime.now(timezone.utc)
    reminded = 0

    rows = conn.execute(
        """
        SELECT r.*
        FROM requests r
        WHERE r.status = 'pending'
        """
    ).fetchall()

    for row in rows:
        req = dict(row)
        created_dt = _parse_request_datetime(req.get("created_at"))
        age_days = max((now - created_dt).days, 0)
        if age_days < min_age_days:
            continue

        existing_note = req.get("admin_note") or ""
        if PENDING_REMINDER_MARKER in existing_note:
            continue

        reminder_note = f"{PENDING_REMINDER_MARKER} Pending approval for {age_days} days."
        merged_note = f"{existing_note}\n\n{reminder_note}".strip() if existing_note else reminder_note

        conn.execute(
            "UPDATE requests SET admin_note = ?, updated_at = ? WHERE id = ?",
            (merged_note, now.isoformat(), req["id"]),
        )
        conn.execute(
            """INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
               VALUES (?, ?, ?, 'system', ?)""",
            (req["id"], req["status"], req["status"], reminder_note),
        )
        reminded += 1

    conn.commit()
    return {"reminded": reminded}


def run_stale_denied_auto_close(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    min_age_days: int = DENIED_AUTO_CLOSE_MIN_AGE_DAYS,
) -> dict:
    """Mark stale denied requests as auto-closed for cleaner admin queue handling."""
    now = now or datetime.now(timezone.utc)
    auto_closed = 0

    rows = conn.execute(
        """
        SELECT r.*
        FROM requests r
        WHERE r.status = 'denied'
        """
    ).fetchall()

    for row in rows:
        req = dict(row)
        updated_dt = _parse_request_datetime(req.get("updated_at") or req.get("created_at"))
        age_days = max((now - updated_dt).days, 0)
        if age_days < min_age_days:
            continue

        existing_note = req.get("admin_note") or ""
        if DENIED_AUTO_CLOSE_MARKER in existing_note:
            continue

        close_note = f"{DENIED_AUTO_CLOSE_MARKER} Denied request closed after {age_days} days without changes."
        merged_note = f"{existing_note}\n\n{close_note}".strip() if existing_note else close_note

        conn.execute(
            "UPDATE requests SET admin_note = ?, updated_at = ? WHERE id = ?",
            (merged_note, now.isoformat(), req["id"]),
        )
        conn.execute(
            """INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
               VALUES (?, ?, ?, 'system', ?)""",
            (req["id"], req["status"], req["status"], close_note),
        )
        auto_closed += 1

    conn.commit()
    return {"auto_closed_denied": auto_closed}


def run_request_lifecycle_rules(
    conn: sqlite3.Connection,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)

    escalation_result = run_high_demand_escalation(conn, now=now)
    reminder_result = run_pending_approval_reminders(conn, now=now)
    auto_close_result = run_stale_denied_auto_close(conn, now=now)

    return {
        "escalated": escalation_result["escalated"],
        "reminded": reminder_result["reminded"],
        "auto_closed_denied": auto_close_result["auto_closed_denied"],
    }


def get_request_stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM requests GROUP BY status"
    ).fetchall()
    stats = {r["status"]: r["count"] for r in rows}
    total = sum(stats.values())
    unique_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM request_supporters"
    ).fetchone()[0]

    now = datetime.now(timezone.utc)
    open_rows = conn.execute(
        "SELECT created_at FROM requests WHERE status IN ('pending', 'approved')"
    ).fetchall()
    open_ages = [max((now - _parse_request_datetime(r["created_at"])).days, 0) for r in open_rows]

    escalated_open = conn.execute(
        """
        SELECT COUNT(*)
        FROM requests
        WHERE status IN ('pending', 'approved')
          AND admin_note LIKE ?
        """,
        (f"%{ESCALATION_MARKER}%",),
    ).fetchone()[0]

    closed_denied = conn.execute(
        """
        SELECT COUNT(*)
        FROM requests
        WHERE status = 'denied'
          AND admin_note LIKE ?
        """,
        (f"%{DENIED_AUTO_CLOSE_MARKER}%",),
    ).fetchone()[0]

    return {
        "total": total,
        "pending": stats.get("pending", 0),
        "approved": stats.get("approved", 0),
        "denied": stats.get("denied", 0),
        "fulfilled": stats.get("fulfilled", 0),
        "unique_users": unique_users,
        "open_over_3_days": sum(1 for age in open_ages if age >= 3),
        "open_over_7_days": sum(1 for age in open_ages if age >= 7),
        "open_over_14_days": sum(1 for age in open_ages if age >= 14),
        "oldest_open_days": max(open_ages) if open_ages else 0,
        "escalated_open": escalated_open,
        "closed_denied": closed_denied,
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
    _create_request_notifications(
        conn,
        request_id,
        event_type="status_changed",
        message=f"Request moved from {old_status} to fulfilled.",
        actor_user_id="system",
        actor_name="System",
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
