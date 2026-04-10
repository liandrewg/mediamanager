import sqlite3
import math
import statistics
from datetime import datetime, timezone, timedelta

from app.config import settings


OPEN_REQUEST_STATUSES = ("pending", "approved")
ESCALATION_MIN_SUPPORTERS = 3
ESCALATION_MIN_AGE_DAYS = 10
ESCALATION_MARKER = "[AUTO-ESCALATED]"
DUPLICATE_MERGE_MARKER = "[DUPLICATE-MERGE]"
DUPLICATE_SOURCE_MERGED_MARKER = "[DUPLICATE-MERGED]"

PENDING_REMINDER_MIN_AGE_DAYS = 3
PENDING_REMINDER_MARKER = "[AUTO-PENDING-REMINDER]"
DENIED_AUTO_CLOSE_MIN_AGE_DAYS = 14
DENIED_AUTO_CLOSE_MARKER = "[AUTO-CLOSED-DENIED]"
SLA_ESCALATION_MARKER = "[SLA-ESCALATION]"

DEFAULT_SLA_WARNING_DAYS = 2


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
    req["queue_position"] = None
    req["queue_size"] = None
    req["queue_ahead_count"] = None
    req["approved_ahead_count"] = None
    req["pending_ahead_count"] = None
    req["supporters_ahead_count"] = None
    req["queue_band"] = None
    req["queue_reason"] = None
    req["blocker_label"] = None
    req["next_step_label"] = None
    req["next_step_by"] = None

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


def _estimate_median_fulfillment_days(conn: sqlite3.Connection) -> float | None:
    try:
        rows = conn.execute(
            """
            SELECT r.created_at AS req_created, rh.created_at AS fulfilled_at
            FROM request_history rh
            JOIN requests r ON r.id = rh.request_id
            WHERE rh.new_status = 'fulfilled'
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    lead_times: list[float] = []
    for row in rows:
        req_dt = _parse_request_datetime(row["req_created"])
        ful_dt = _parse_request_datetime(row["fulfilled_at"])
        if ful_dt >= req_dt:
            lead_times.append((ful_dt - req_dt).total_seconds() / 86400.0)

    if not lead_times:
        return None
    return statistics.median(lead_times)


def _estimate_fulfillment_window(conn: sqlite3.Connection) -> dict | None:
    try:
        rows = conn.execute(
            """
            SELECT r.created_at AS req_created, rh.created_at AS fulfilled_at
            FROM request_history rh
            JOIN requests r ON r.id = rh.request_id
            WHERE rh.new_status = 'fulfilled'
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    lead_times: list[float] = []
    for row in rows:
        req_dt = _parse_request_datetime(row["req_created"])
        ful_dt = _parse_request_datetime(row["fulfilled_at"])
        if ful_dt >= req_dt:
            lead_times.append((ful_dt - req_dt).total_seconds() / 86400.0)

    if not lead_times:
        return None

    lead_times.sort()

    def _percentile(values: list[float], pct: float) -> float:
        if len(values) == 1:
            return values[0]
        position = (len(values) - 1) * pct
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[int(position)]
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    p50 = _percentile(lead_times, 0.5)
    p80 = _percentile(lead_times, 0.8)
    sample_size = len(lead_times)
    confidence = "high" if sample_size >= 15 else ("medium" if sample_size >= 6 else "low")

    return {
        "sample_size": sample_size,
        "p50_days": p50,
        "p80_days": p80,
        "confidence": confidence,
    }


def _iso_after_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=max(days, 0))).date().isoformat()


def _build_next_step_hint(
    *,
    req: dict,
    policy_target_days: int,
    median_fulfillment_days: float | None,
) -> tuple[str | None, str | None]:
    status = req.get("status")
    days_open = int(req.get("days_open") or 0)
    queue_position = req.get("queue_position")

    if status == "pending":
        remaining = max(policy_target_days - days_open, 0)
        queue_text = f" (queue #{queue_position})" if queue_position else ""
        return (
            f"Admin review expected within {remaining}d{queue_text}",
            _iso_after_days(remaining),
        )

    if status == "approved":
        if median_fulfillment_days is not None:
            remaining = max(int(round(median_fulfillment_days)) - days_open, 0)
            return (
                f"Typical fulfillment in ~{remaining}d based on household history",
                _iso_after_days(remaining),
            )
        return ("Approved, waiting for library availability", None)

    if status == "fulfilled":
        return ("Ready to watch now", None)

    if status == "denied":
        return ("Denied, request a similar title to reopen demand", None)

    return (None, None)


def _build_queue_transparency_context(open_rows: list[sqlite3.Row]) -> dict[int, dict]:
    queue_size = len(open_rows)
    contexts: dict[int, dict] = {}

    for idx, row in enumerate(open_rows):
        request_id = row["id"]
        queue_position = idx + 1
        ahead_rows = open_rows[:idx]
        ahead_count = len(ahead_rows)
        approved_ahead = sum(1 for ahead in ahead_rows if ahead["status"] == "approved")
        pending_ahead = ahead_count - approved_ahead
        supporters_ahead = sum(int(ahead["supporter_count"] or 0) for ahead in ahead_rows)

        if queue_position == 1:
            queue_band = "up_next"
            queue_reason = "You are first in line right now."
        elif queue_position <= 3:
            queue_band = "near_front"
            queue_reason = f"Only {ahead_count} request{'s' if ahead_count != 1 else ''} ahead of you."
        elif queue_position <= max(5, math.ceil(queue_size * 0.35)):
            queue_band = "in_pack"
            queue_reason = f"Mid-pack, with {ahead_count} requests ahead of you."
        else:
            queue_band = "long_tail"
            queue_reason = f"Lower in the household queue, with {ahead_count} requests ahead of you."

        blocker_bits: list[str] = []
        if approved_ahead:
            blocker_bits.append(f"{approved_ahead} already approved")
        if pending_ahead:
            blocker_bits.append(f"{pending_ahead} still waiting for review")
        if supporters_ahead:
            blocker_bits.append(f"{supporters_ahead} total supporters ahead")

        contexts[request_id] = {
            "queue_position": queue_position,
            "queue_size": queue_size,
            "queue_ahead_count": ahead_count,
            "approved_ahead_count": approved_ahead,
            "pending_ahead_count": pending_ahead,
            "supporters_ahead_count": supporters_ahead,
            "queue_band": queue_band,
            "queue_reason": queue_reason,
            "blocker_label": "Ahead of you: " + ", ".join(blocker_bits) if blocker_bits else None,
        }

    return contexts


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


def _normalize_title(title: str | None) -> str:
    return " ".join((title or "").casefold().split())


def _append_admin_note(existing_note: str | None, new_note: str) -> str:
    note = (existing_note or "").strip()
    if not note:
        return new_note
    return f"{note}\n\n{new_note}"


def _create_request_notifications_for_users(
    conn: sqlite3.Connection,
    request_id: int,
    user_ids: set[str] | list[str],
    event_type: str,
    message: str,
    actor_user_id: str | None = None,
    actor_name: str | None = None,
) -> int:
    created = 0
    try:
        for user_id in sorted(set(user_ids)):
            conn.execute(
                """
                INSERT INTO request_notifications (request_id, user_id, type, message, actor_user_id, actor_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, user_id, event_type, message, actor_user_id, actor_name),
            )
            created += 1
    except sqlite3.OperationalError:
        return 0
    return created


def _add_system_comment(
    conn: sqlite3.Connection,
    request_id: int,
    body: str,
    created_at: str,
) -> None:
    try:
        conn.execute(
            """
            INSERT INTO request_comments (request_id, user_id, username, is_admin, body, created_at)
            VALUES (?, 'system', 'System', 1, ?, ?)
            """,
            (request_id, body, created_at),
        )
    except sqlite3.OperationalError:
        return


def get_sla_policy(conn: sqlite3.Connection) -> dict:
    default_target = max(int(getattr(settings, "request_sla_days", 7) or 7), 1)
    default_warning = min(DEFAULT_SLA_WARNING_DAYS, max(default_target - 1, 0))
    try:
        row = conn.execute(
            """
            SELECT target_days, warning_days, updated_at
            FROM sla_policy
            WHERE id = 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        row = None

    if not row:
        return {
            "target_days": default_target,
            "warning_days": default_warning,
            "updated_at": None,
        }

    target_days = max(int(row["target_days"] or default_target), 1)
    warning_days = min(max(int(row["warning_days"] or 0), 0), max(target_days - 1, 0))
    return {
        "target_days": target_days,
        "warning_days": warning_days,
        "updated_at": row["updated_at"],
    }


def update_sla_policy(
    conn: sqlite3.Connection,
    target_days: int,
    warning_days: int,
) -> dict:
    target_days = max(int(target_days or 1), 1)
    warning_days = min(max(int(warning_days or 0), 0), max(target_days - 1, 0))
    now = datetime.utcnow().isoformat()

    try:
        conn.execute(
            """
            INSERT INTO sla_policy (id, target_days, warning_days, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                target_days = excluded.target_days,
                warning_days = excluded.warning_days,
                updated_at = excluded.updated_at
            """,
            (target_days, warning_days, now),
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()

    return get_sla_policy(conn)


def get_sla_worklist(
    conn: sqlite3.Connection,
    state: str = "all",
    limit: int = 200,
) -> dict:
    policy = get_sla_policy(conn)
    target_days = policy["target_days"]
    warning_days = policy["warning_days"]

    rows = conn.execute(
        """
        SELECT *
        FROM requests
        WHERE status IN ('pending', 'approved')
        ORDER BY created_at ASC
        """
    ).fetchall()

    items: list[dict] = []
    for row in rows:
        serialized = _serialize_request(conn, row)
        days_open = serialized.get("days_open", 0)
        days_until_breach = target_days - days_open
        if days_until_breach < 0:
            sla_state = "breached"
        elif days_until_breach <= warning_days:
            sla_state = "due_soon"
        else:
            sla_state = "on_track"

        serialized["sla_target_days"] = target_days
        serialized["sla_warning_days"] = warning_days
        serialized["days_until_breach"] = days_until_breach
        serialized["sla_state"] = sla_state
        items.append(serialized)

    summary = {
        "breached": sum(1 for item in items if item["sla_state"] == "breached"),
        "due_soon": sum(1 for item in items if item["sla_state"] == "due_soon"),
        "on_track": sum(1 for item in items if item["sla_state"] == "on_track"),
        "total_open": len(items),
    }

    if state != "all":
        items = [item for item in items if item["sla_state"] == state]

    items.sort(
        key=lambda item: (
            0 if item["sla_state"] == "breached" else (1 if item["sla_state"] == "due_soon" else 2),
            item["days_until_breach"],
            -item["supporter_count"],
            -item["days_open"],
        )
    )

    bounded_limit = min(max(int(limit or 1), 1), 1000)
    return {
        "policy": policy,
        "summary": summary,
        "state": state,
        "items": items[:bounded_limit],
    }


def bulk_escalate_sla_breaches(
    conn: sqlite3.Connection,
    request_ids: list[int],
    changed_by: str,
    note: str | None = None,
) -> dict:
    if not request_ids:
        return {"updated": [], "missing": []}

    now = datetime.utcnow().isoformat()
    actor_name = _resolve_actor_name(conn, changed_by)
    policy = get_sla_policy(conn)

    updated: list[dict] = []
    missing: list[int] = []
    for request_id in request_ids:
        row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            missing.append(request_id)
            continue

        req = dict(row)
        if req["status"] not in OPEN_REQUEST_STATUSES:
            continue

        days_open = max((datetime.now(timezone.utc) - _parse_request_datetime(req.get("created_at"))).days, 0)
        marker_note = (
            f"{SLA_ESCALATION_MARKER} Escalated after {days_open} days open "
            f"(SLA target: {policy['target_days']}d)."
        )
        full_note = marker_note if not note else f"{marker_note} {note.strip()}"
        merged_note = _append_admin_note(req.get("admin_note"), full_note)

        conn.execute(
            "UPDATE requests SET admin_note = ?, updated_at = ? WHERE id = ?",
            (merged_note, now, request_id),
        )
        conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, req["status"], req["status"], changed_by, full_note),
        )
        _add_system_comment(conn, request_id, full_note, now)
        _create_request_notifications(
            conn,
            request_id,
            event_type="sla_escalated",
            message=f"Request received SLA escalation attention from {actor_name}.",
            actor_user_id=changed_by,
            actor_name=actor_name,
        )
        updated.append(get_request_by_id(conn, request_id))

    conn.commit()
    return {"updated": updated, "missing": missing}


def _get_active_duplicate_candidate_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM request_supporters s WHERE s.request_id = r.id) as supporter_count
        FROM requests r
        WHERE r.status IN ('pending', 'approved')
        ORDER BY CASE r.status WHEN 'approved' THEN 0 ELSE 1 END, r.created_at ASC, r.id ASC
        """
    ).fetchall()


def _build_duplicate_groups(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
) -> list[dict]:
    if len(rows) < 2:
        return []

    items: list[dict] = []
    parent: dict[int, int] = {}
    title_groups: dict[tuple[str, str], list[int]] = {}
    tmdb_groups: dict[tuple[str, int], list[int]] = {}

    for row in rows:
        item = dict(row)
        item["normalized_title"] = _normalize_title(item.get("title"))
        items.append(item)
        parent[item["id"]] = item["id"]
        title_groups.setdefault((item["media_type"], item["normalized_title"]), []).append(item["id"])
        tmdb_groups.setdefault((item["media_type"], item["tmdb_id"]), []).append(item["id"])

    def find(request_id: int) -> int:
        while parent[request_id] != request_id:
            parent[request_id] = parent[parent[request_id]]
            request_id = parent[request_id]
        return request_id

    def union(left_id: int, right_id: int) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root != right_root:
            parent[right_root] = left_root

    for request_ids in title_groups.values():
        anchor = request_ids[0]
        for request_id in request_ids[1:]:
            union(anchor, request_id)

    for request_ids in tmdb_groups.values():
        anchor = request_ids[0]
        for request_id in request_ids[1:]:
            union(anchor, request_id)

    grouped_items: dict[int, list[dict]] = {}
    for item in items:
        grouped_items.setdefault(find(item["id"]), []).append(item)

    duplicate_groups: list[dict] = []
    for group_items in grouped_items.values():
        if len(group_items) < 2:
            continue

        group_items.sort(
            key=lambda item: (
                0 if item["status"] == "approved" else 1,
                _parse_request_datetime(item.get("created_at")),
                item["id"],
            )
        )
        title_counts: dict[str, int] = {}
        tmdb_counts: dict[int, int] = {}
        for item in group_items:
            title_counts[item["normalized_title"]] = title_counts.get(item["normalized_title"], 0) + 1
            tmdb_counts[item["tmdb_id"]] = tmdb_counts.get(item["tmdb_id"], 0) + 1

        requests = [_serialize_request(conn, item) for item in group_items]
        duplicate_groups.append(
            {
                "group_id": f"dup-{'-'.join(str(item['id']) for item in group_items)}",
                "media_type": group_items[0]["media_type"],
                "normalized_title": max(
                    title_counts.items(),
                    key=lambda entry: (entry[1], -len(entry[0]), entry[0]),
                )[0],
                "matched_by_title": any(count > 1 for count in title_counts.values()),
                "matched_by_tmdb": any(count > 1 for count in tmdb_counts.values()),
                "shared_tmdb_ids": sorted(tmdb_id for tmdb_id, count in tmdb_counts.items() if count > 1),
                "request_ids": [request["id"] for request in requests],
                "total_supporters": sum(request["supporter_count"] for request in requests),
                "requests": requests,
            }
        )

    duplicate_groups.sort(
        key=lambda group: (
            -len(group["request_ids"]),
            -group["total_supporters"],
            group["media_type"],
            group["request_ids"][0],
        )
    )
    return duplicate_groups


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

    items = [_serialize_request(conn, r, user_id) for r in rows]

    open_rows = conn.execute(
        """
        SELECT r.*, (SELECT COUNT(*) FROM request_supporters s WHERE s.request_id = r.id) as supporter_count
        FROM requests r
        WHERE r.status IN ('pending', 'approved')
        ORDER BY supporter_count DESC, r.created_at ASC, r.id ASC
        """
    ).fetchall()
    queue_context = _build_queue_transparency_context(open_rows)

    policy = get_sla_policy(conn)
    median_fulfillment_days = _estimate_median_fulfillment_days(conn)
    fulfillment_window = _estimate_fulfillment_window(conn)
    for req in items:
        if req.get("status") in OPEN_REQUEST_STATUSES:
            req.update(queue_context.get(req["id"], {}))
        label, next_step_by = _build_next_step_hint(
            req=req,
            policy_target_days=policy["target_days"],
            median_fulfillment_days=median_fulfillment_days,
        )
        req["next_step_label"] = label
        req["next_step_by"] = next_step_by

        req["eta_label"] = None
        req["eta_start"] = None
        req["eta_end"] = None
        req["eta_confidence"] = None

        if req.get("status") == "approved" and fulfillment_window:
            remaining_start = max(int(round(fulfillment_window["p50_days"])) - req["days_open"], 0)
            remaining_end = max(int(math.ceil(fulfillment_window["p80_days"])) - req["days_open"], remaining_start)
            req["eta_start"] = _iso_after_days(remaining_start)
            req["eta_end"] = _iso_after_days(remaining_end)
            req["eta_confidence"] = fulfillment_window["confidence"]

            if remaining_end == 0:
                req["eta_label"] = "Likely available any day now"
            elif remaining_start == remaining_end:
                req["eta_label"] = f"Likely available in ~{remaining_end}d"
            else:
                req["eta_label"] = f"Likely available in {remaining_start}-{remaining_end}d"

    return {
        "items": items,
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


def get_duplicate_request_groups(conn: sqlite3.Connection) -> list[dict]:
    active_rows = _get_active_duplicate_candidate_rows(conn)
    return _build_duplicate_groups(conn, active_rows)


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


def merge_duplicate_requests(
    conn: sqlite3.Connection,
    target_request_id: int,
    source_request_ids: list[int],
    changed_by: str,
) -> dict:
    deduped_source_ids: list[int] = []
    seen_source_ids: set[int] = set()
    for source_id in source_request_ids:
        if source_id == target_request_id:
            raise ValueError("Target request cannot also be listed as a source")
        if source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)
        deduped_source_ids.append(source_id)

    if not deduped_source_ids:
        raise ValueError("At least one source request must be selected")

    requested_ids = [target_request_id, *deduped_source_ids]
    placeholders = ",".join("?" for _ in requested_ids)
    rows = conn.execute(
        f"SELECT * FROM requests WHERE id IN ({placeholders})",
        requested_ids,
    ).fetchall()
    if len(rows) != len(requested_ids):
        found_ids = {row["id"] for row in rows}
        missing_ids = [request_id for request_id in requested_ids if request_id not in found_ids]
        raise ValueError(f"Request not found: {missing_ids[0]}")

    request_rows = {row["id"]: dict(row) for row in rows}
    target_row = request_rows[target_request_id]
    source_rows = [request_rows[source_id] for source_id in deduped_source_ids]

    if any(row["status"] not in OPEN_REQUEST_STATUSES for row in rows):
        raise ValueError("Only pending or approved requests can be merged")

    media_types = {row["media_type"] for row in rows}
    if len(media_types) != 1:
        raise ValueError("Only requests with the same media type can be merged")

    duplicate_groups = get_duplicate_request_groups(conn)
    target_group = next(
        (set(group["request_ids"]) for group in duplicate_groups if target_request_id in group["request_ids"]),
        None,
    )
    if not target_group or any(source_id not in target_group for source_id in deduped_source_ids):
        raise ValueError("Selected requests are not in the same duplicate group")

    ordered_sources = sorted(
        source_rows,
        key=lambda row: (
            _parse_request_datetime(row.get("created_at")),
            row["id"],
        ),
    )
    actor_name = _resolve_actor_name(conn, changed_by)
    now = datetime.utcnow().isoformat()
    merged_rows = [target_row, *ordered_sources]
    earliest_request = min(
        merged_rows,
        key=lambda row: (_parse_request_datetime(row.get("created_at")), row["id"]),
    )
    target_note_seed = (target_row.get("admin_note") or "").strip()
    if not target_note_seed:
        for source_row in ordered_sources:
            source_note = (source_row.get("admin_note") or "").strip()
            if source_note:
                target_note_seed = source_note
                break

    source_summary = ", ".join(f"#{row['id']} \"{row['title']}\"" for row in ordered_sources)
    merge_note = (
        f"{DUPLICATE_MERGE_MARKER} Consolidated duplicate requests into canonical request "
        f"#{target_request_id}: {source_summary}."
    )
    target_note = _append_admin_note(target_note_seed, merge_note)
    source_admin_note = (
        f"{DUPLICATE_SOURCE_MERGED_MARKER} Merged into request "
        f"#{target_request_id} ({target_row['title']}). Support moved to the canonical request."
    )

    supporter_rows = conn.execute(
        f"""
        SELECT request_id, user_id, username, created_at
        FROM request_supporters
        WHERE request_id IN ({placeholders})
        ORDER BY created_at ASC, id ASC
        """,
        requested_ids,
    ).fetchall()
    source_impacted_user_ids: set[str] = set()
    supporters_by_user: dict[str, dict] = {}
    for supporter_row in supporter_rows:
        supporter = dict(supporter_row)
        if supporter["request_id"] in deduped_source_ids:
            source_impacted_user_ids.add(supporter["user_id"])

        existing = supporters_by_user.get(supporter["user_id"])
        supporter_created_at = _parse_request_datetime(supporter.get("created_at"))
        if not existing:
            supporters_by_user[supporter["user_id"]] = supporter
            continue

        existing_created_at = _parse_request_datetime(existing.get("created_at"))
        if supporter_created_at < existing_created_at:
            supporters_by_user[supporter["user_id"]] = supporter

    target_supporter_rows = conn.execute(
        """
        SELECT id, user_id, username, created_at
        FROM request_supporters
        WHERE request_id = ?
        """,
        (target_request_id,),
    ).fetchall()
    target_supporters = {row["user_id"]: dict(row) for row in target_supporter_rows}

    try:
        for user_id, supporter in supporters_by_user.items():
            if user_id in target_supporters:
                conn.execute(
                    """
                    UPDATE request_supporters
                    SET username = ?, created_at = ?
                    WHERE request_id = ? AND user_id = ?
                    """,
                    (
                        supporter["username"],
                        supporter["created_at"],
                        target_request_id,
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO request_supporters (request_id, user_id, username, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        target_request_id,
                        user_id,
                        supporter["username"],
                        supporter["created_at"],
                    ),
                )

        source_placeholders = ",".join("?" for _ in deduped_source_ids)
        conn.execute(
            f"DELETE FROM request_supporters WHERE request_id IN ({source_placeholders})",
            deduped_source_ids,
        )

        target_poster_path = target_row.get("poster_path") or next(
            (row.get("poster_path") for row in ordered_sources if row.get("poster_path")),
            None,
        )
        conn.execute(
            """
            UPDATE requests
            SET poster_path = ?, admin_note = ?, created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                target_poster_path,
                target_note,
                earliest_request["created_at"],
                now,
                target_request_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (target_request_id, target_row["status"], target_row["status"], changed_by, merge_note),
        )
        _add_system_comment(conn, target_request_id, merge_note, now)

        for source_row in ordered_sources:
            conn.execute(
                """
                UPDATE requests
                SET status = 'denied', admin_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (source_admin_note, now, source_row["id"]),
            )
            conn.execute(
                """
                INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
                VALUES (?, ?, 'denied', ?, ?)
                """,
                (source_row["id"], source_row["status"], changed_by, source_admin_note),
            )

        notifications_created = _create_request_notifications_for_users(
            conn,
            target_request_id,
            source_impacted_user_ids,
            event_type="request_merged",
            message=(
                f"Your duplicate request support was merged into request "
                f"#{target_request_id} ({target_row['title']})."
            ),
            actor_user_id=changed_by,
            actor_name=actor_name,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "target": get_request_by_id(conn, target_request_id),
        "merged_source_ids": deduped_source_ids,
        "notifications_created": notifications_created,
    }


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
