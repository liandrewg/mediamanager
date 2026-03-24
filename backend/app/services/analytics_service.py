import sqlite3
import statistics
from datetime import datetime, timezone


ESCALATION_MARKER = "[AUTO-ESCALATED]"


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    for parser in (
        datetime.fromisoformat,
        lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parser(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, TypeError):
            continue
    return None


def get_analytics(conn: sqlite3.Connection) -> dict:
    # Ensure rows are accessible by column name
    original_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        return _compute_analytics(conn)
    finally:
        conn.row_factory = original_factory


def _compute_analytics(conn: sqlite3.Connection) -> dict:
    # --- Summary KPIs ---
    total_requests_all_time = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    fulfilled_all_time = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status = 'fulfilled'"
    ).fetchone()[0]

    fulfillment_rate = (
        round(fulfilled_all_time / total_requests_all_time * 100, 1)
        if total_requests_all_time > 0
        else 0.0
    )

    # --- Lead time (days from request created_at to fulfilled history entry) ---
    history_rows = conn.execute(
        """
        SELECT r.created_at AS req_created, rh.created_at AS fulfilled_at
        FROM request_history rh
        JOIN requests r ON r.id = rh.request_id
        WHERE rh.new_status = 'fulfilled'
        """
    ).fetchall()

    lead_times: list[float] = []
    for row in history_rows:
        req_dt = _parse_dt(row["req_created"])
        ful_dt = _parse_dt(row["fulfilled_at"])
        if req_dt and ful_dt and ful_dt >= req_dt:
            delta = (ful_dt - req_dt).total_seconds() / 86400.0
            lead_times.append(delta)

    avg_lead_time_days: float | None = None
    median_lead_time_days: float | None = None
    p90_lead_time_days: float | None = None

    if lead_times:
        avg_lead_time_days = round(sum(lead_times) / len(lead_times), 1)
        median_lead_time_days = round(statistics.median(lead_times), 1)
        if len(lead_times) >= 10:
            # statistics.quantiles requires at least 2 data points; n=10 for deciles
            p90_lead_time_days = round(statistics.quantiles(lead_times, n=10)[8], 1)
        else:
            p90_lead_time_days = round(max(lead_times), 1)

    # --- Backlog pressure ---
    open_count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status IN ('pending', 'approved')"
    ).fetchone()[0]
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status = 'pending'"
    ).fetchone()[0]
    approved_count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status = 'approved'"
    ).fetchone()[0]
    denied_count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status = 'denied'"
    ).fetchone()[0]
    escalated_count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status IN ('pending', 'approved') AND admin_note LIKE ?",
        (f"%{ESCALATION_MARKER}%",),
    ).fetchone()[0]

    now = datetime.now(timezone.utc)
    open_rows = conn.execute(
        "SELECT created_at FROM requests WHERE status IN ('pending', 'approved')"
    ).fetchall()
    open_ages = []
    for row in open_rows:
        dt = _parse_dt(row["created_at"])
        if dt:
            open_ages.append(max((now - dt).days, 0))
    oldest_open_days = max(open_ages) if open_ages else 0

    # --- Top requesters (top 5 by total requests ever as original requester) ---
    top_requester_rows = conn.execute(
        """
        SELECT username, COUNT(*) as cnt
        FROM requests
        GROUP BY username
        ORDER BY cnt DESC
        LIMIT 5
        """
    ).fetchall()
    top_requesters = [{"username": r["username"], "count": r["cnt"]} for r in top_requester_rows]

    # --- Media type breakdown ---
    media_type_rows = conn.execute(
        """
        SELECT media_type,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'fulfilled' THEN 1 ELSE 0 END) as fulfilled
        FROM requests
        GROUP BY media_type
        ORDER BY total DESC
        """
    ).fetchall()
    by_media_type = [
        {"media_type": r["media_type"], "total": r["total"], "fulfilled": r["fulfilled"] or 0}
        for r in media_type_rows
    ]

    # --- Monthly request volume (last 12 months) ---
    monthly_rows = conn.execute(
        """
        SELECT strftime('%Y-%m', created_at) as month,
               COUNT(*) as submitted,
               SUM(CASE WHEN status = 'fulfilled' THEN 1 ELSE 0 END) as fulfilled
        FROM requests
        WHERE created_at >= date('now', '-12 months')
        GROUP BY month
        ORDER BY month ASC
        """
    ).fetchall()
    monthly_volume = [
        {"month": r["month"], "submitted": r["submitted"], "fulfilled": r["fulfilled"] or 0}
        for r in monthly_rows
    ]

    # --- Weekly throughput: fulfilled per week (last 8 weeks) ---
    weekly_rows = conn.execute(
        """
        SELECT strftime('%Y-W%W', rh.created_at) as week,
               COUNT(*) as fulfilled
        FROM request_history rh
        WHERE rh.new_status = 'fulfilled'
          AND rh.created_at >= date('now', '-56 days')
        GROUP BY week
        ORDER BY week ASC
        """
    ).fetchall()
    weekly_throughput = [{"week": r["week"], "fulfilled": r["fulfilled"]} for r in weekly_rows]

    # --- Supporter engagement ---
    total_supporters_ever = conn.execute(
        "SELECT COUNT(*) FROM request_supporters"
    ).fetchone()[0]

    avg_supporters_per_request: float = 0.0
    if total_requests_all_time > 0:
        avg_supporters_per_request = round(total_supporters_ever / total_requests_all_time, 2)

    return {
        "total_requests_all_time": total_requests_all_time,
        "fulfilled_all_time": fulfilled_all_time,
        "fulfillment_rate": fulfillment_rate,
        "avg_lead_time_days": avg_lead_time_days,
        "median_lead_time_days": median_lead_time_days,
        "p90_lead_time_days": p90_lead_time_days,
        "open_count": open_count,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "denied_count": denied_count,
        "escalated_count": escalated_count,
        "oldest_open_days": oldest_open_days,
        "top_requesters": top_requesters,
        "by_media_type": by_media_type,
        "monthly_volume": monthly_volume,
        "weekly_throughput": weekly_throughput,
        "total_supporters_ever": total_supporters_ever,
        "avg_supporters_per_request": avg_supporters_per_request,
    }
