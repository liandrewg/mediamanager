import math
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


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    sorted_vals = sorted(values)
    rank = (len(sorted_vals) - 1) * percentile
    lower_idx = math.floor(rank)
    upper_idx = math.ceil(rank)

    if lower_idx == upper_idx:
        return sorted_vals[lower_idx]

    weight = rank - lower_idx
    return sorted_vals[lower_idx] + (sorted_vals[upper_idx] - sorted_vals[lower_idx]) * weight


def get_analytics(conn: sqlite3.Connection, sla_days: int = 7) -> dict:
    # Ensure rows are accessible by column name
    original_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        return _compute_analytics(conn, sla_days=max(int(sla_days or 7), 1))
    finally:
        conn.row_factory = original_factory


def get_sla_target_simulation(
    conn: sqlite3.Connection,
    target_days: list[int],
    current_target_days: int | None = None,
) -> dict:
    original_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        return _compute_sla_target_simulation(conn, target_days, current_target_days=current_target_days)
    finally:
        conn.row_factory = original_factory


def _compute_analytics(conn: sqlite3.Connection, sla_days: int) -> dict:
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
        SELECT r.created_at AS req_created, rh.created_at AS fulfilled_at, r.media_type AS media_type
        FROM request_history rh
        JOIN requests r ON r.id = rh.request_id
        WHERE rh.new_status = 'fulfilled'
        """
    ).fetchall()

    lead_times: list[float] = []
    lead_times_by_media_type: dict[str, list[float]] = {}
    for row in history_rows:
        req_dt = _parse_dt(row["req_created"])
        ful_dt = _parse_dt(row["fulfilled_at"])
        if req_dt and ful_dt and ful_dt >= req_dt:
            delta = (ful_dt - req_dt).total_seconds() / 86400.0
            lead_times.append(delta)
            media_type = row["media_type"] or "unknown"
            lead_times_by_media_type.setdefault(media_type, []).append(delta)

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

    fulfilled_within_sla_count = sum(1 for value in lead_times if value <= sla_days)
    fulfilled_outside_sla_count = max(len(lead_times) - fulfilled_within_sla_count, 0)
    fulfilled_within_sla_rate = (
        round(fulfilled_within_sla_count / len(lead_times) * 100, 1)
        if lead_times
        else 0.0
    )

    # --- Weekly SLA trend (last 8 weeks) ---
    weekly_sla_buckets: dict[str, dict[str, int]] = {}
    weekly_window_now = datetime.now(timezone.utc)
    for row in history_rows:
        req_dt = _parse_dt(row["req_created"])
        ful_dt = _parse_dt(row["fulfilled_at"])
        if not req_dt or not ful_dt or ful_dt < req_dt:
            continue
        if (weekly_window_now - ful_dt).days > 56:
            continue

        week_key = ful_dt.strftime("%Y-W%W")
        bucket = weekly_sla_buckets.setdefault(week_key, {"within": 0, "total": 0})
        bucket["total"] += 1
        if ((ful_dt - req_dt).total_seconds() / 86400.0) <= sla_days:
            bucket["within"] += 1

    weekly_sla_hit_rate = []
    for week in sorted(weekly_sla_buckets.keys()):
        bucket = weekly_sla_buckets[week]
        total = bucket["total"]
        rate = round(bucket["within"] / total * 100, 1) if total else 0.0
        weekly_sla_hit_rate.append(
            {
                "week": week,
                "within_sla": bucket["within"],
                "fulfilled": total,
                "hit_rate": rate,
            }
        )

    sla_trend_direction = "flat"
    sla_trend_delta = 0.0
    if len(weekly_sla_hit_rate) >= 2:
        sla_trend_delta = round(
            weekly_sla_hit_rate[-1]["hit_rate"] - weekly_sla_hit_rate[0]["hit_rate"],
            1,
        )
        if sla_trend_delta >= 5:
            sla_trend_direction = "improving"
        elif sla_trend_delta <= -5:
            sla_trend_direction = "regressing"

    # --- SLA recommendation (answers: what should our household target be?) ---
    recommended_sla_days: int | None = None
    recommended_sla_within_rate: float | None = None
    if lead_times:
        p75 = _percentile(lead_times, 0.75)
        if p75 is not None:
            # Use p75 as a practical target that keeps expectations realistic
            recommended_sla_days = max(1, math.ceil(p75))
            within_recommended = sum(1 for value in lead_times if value <= recommended_sla_days)
            recommended_sla_within_rate = round(within_recommended / len(lead_times) * 100, 1)

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
    open_breaching_sla = sum(1 for age in open_ages if age > sla_days)
    open_due_soon = sum(1 for age in open_ages if max(sla_days - age, 0) <= 2 and age <= sla_days)
    open_breaching_recommended_sla = (
        sum(1 for age in open_ages if age > recommended_sla_days)
        if recommended_sla_days is not None
        else None
    )

    open_rows_with_type = conn.execute(
        "SELECT media_type, created_at FROM requests WHERE status IN ('pending', 'approved')"
    ).fetchall()
    open_ages_by_media_type: dict[str, list[int]] = {}
    for row in open_rows_with_type:
        dt = _parse_dt(row["created_at"])
        if not dt:
            continue
        media_type = row["media_type"] or "unknown"
        open_ages_by_media_type.setdefault(media_type, []).append(max((now - dt).days, 0))

    media_type_sla_insights: list[dict] = []
    for media_type in sorted(set(list(lead_times_by_media_type.keys()) + list(open_ages_by_media_type.keys()))):
        media_leads = sorted(lead_times_by_media_type.get(media_type, []))
        sample_size = len(media_leads)
        median_days = round(statistics.median(media_leads), 1) if media_leads else None

        recommended_target_days = None
        recommended_hit_rate = None
        if media_leads:
            media_p75 = _percentile(media_leads, 0.75)
            if media_p75 is not None:
                recommended_target_days = max(1, math.ceil(media_p75))
                within = sum(1 for value in media_leads if value <= recommended_target_days)
                recommended_hit_rate = round(within / sample_size * 100, 1)

        open_media_ages = open_ages_by_media_type.get(media_type, [])
        open_count_for_type = len(open_media_ages)
        open_breaching_global_policy = sum(1 for age in open_media_ages if age > sla_days)
        open_breaching_recommended = (
            sum(1 for age in open_media_ages if age > recommended_target_days)
            if recommended_target_days is not None
            else None
        )

        media_type_sla_insights.append(
            {
                "media_type": media_type,
                "fulfilled_sample_size": sample_size,
                "median_lead_time_days": median_days,
                "recommended_target_days": recommended_target_days,
                "recommended_within_rate": recommended_hit_rate,
                "open_count": open_count_for_type,
                "open_breaching_global_policy": open_breaching_global_policy,
                "open_breaching_recommended": open_breaching_recommended,
            }
        )

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
        "sla_days": sla_days,
        "fulfilled_within_sla_count": fulfilled_within_sla_count,
        "fulfilled_outside_sla_count": fulfilled_outside_sla_count,
        "fulfilled_within_sla_rate": fulfilled_within_sla_rate,
        "recommended_sla_days": recommended_sla_days,
        "recommended_sla_within_rate": recommended_sla_within_rate,
        "recommended_sla_sample_size": len(lead_times),
        "open_count": open_count,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "denied_count": denied_count,
        "escalated_count": escalated_count,
        "oldest_open_days": oldest_open_days,
        "open_breaching_sla": open_breaching_sla,
        "open_breaching_recommended_sla": open_breaching_recommended_sla,
        "open_due_soon": open_due_soon,
        "media_type_sla_insights": media_type_sla_insights,
        "top_requesters": top_requesters,
        "by_media_type": by_media_type,
        "monthly_volume": monthly_volume,
        "weekly_throughput": weekly_throughput,
        "weekly_sla_hit_rate": weekly_sla_hit_rate,
        "sla_trend_delta": sla_trend_delta,
        "sla_trend_direction": sla_trend_direction,
        "total_supporters_ever": total_supporters_ever,
        "avg_supporters_per_request": avg_supporters_per_request,
    }


def _compute_sla_target_simulation(
    conn: sqlite3.Connection,
    targets: list[int],
    current_target_days: int | None = None,
) -> dict:
    normalized_targets = sorted({max(int(target), 1) for target in targets if int(target) > 0})
    if not normalized_targets:
        normalized_targets = [7]

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
            lead_times.append((ful_dt - req_dt).total_seconds() / 86400.0)

    now = datetime.now(timezone.utc)
    open_rows = conn.execute(
        "SELECT created_at FROM requests WHERE status IN ('pending', 'approved')"
    ).fetchall()
    open_ages: list[int] = []
    for row in open_rows:
        dt = _parse_dt(row["created_at"])
        if dt:
            open_ages.append(max((now - dt).days, 0))

    def _risk_score(*, breached: int, due_soon: int, hit_rate: float | None) -> float:
        miss_rate = 50.0 if hit_rate is None else max(0.0, 100.0 - hit_rate)
        return round((breached * 100.0) + (due_soon * 35.0) + (miss_rate * 0.5), 1)

    scenarios: list[dict] = []
    for target in normalized_targets:
        warning_days = min(max(target - 2, 0), max(target - 1, 0))
        if lead_times:
            within = sum(1 for value in lead_times if value <= target)
            hit_rate = round(within / len(lead_times) * 100, 1)
        else:
            within = 0
            hit_rate = None

        breached = sum(1 for age in open_ages if age > target)
        due_soon = sum(1 for age in open_ages if target - warning_days <= age <= target)
        scenarios.append(
            {
                "target_days": target,
                "warning_days": warning_days,
                "historical_hit_rate": hit_rate,
                "historical_within_count": within,
                "historical_sample_size": len(lead_times),
                "open_breaching": breached,
                "open_due_soon": due_soon,
                "operational_risk_score": _risk_score(breached=breached, due_soon=due_soon, hit_rate=hit_rate),
            }
        )

    current_target = max(int(current_target_days), 1) if current_target_days else None
    baseline_scenario = next((row for row in scenarios if row["target_days"] == current_target), None)

    if baseline_scenario is None and current_target is not None:
        warning_days = min(max(current_target - 2, 0), max(current_target - 1, 0))
        if lead_times:
            within = sum(1 for value in lead_times if value <= current_target)
            hit_rate = round(within / len(lead_times) * 100, 1)
        else:
            within = 0
            hit_rate = None
        breached = sum(1 for age in open_ages if age > current_target)
        due_soon = sum(1 for age in open_ages if current_target - warning_days <= age <= current_target)
        baseline_scenario = {
            "target_days": current_target,
            "warning_days": warning_days,
            "historical_hit_rate": hit_rate,
            "historical_within_count": within,
            "historical_sample_size": len(lead_times),
            "open_breaching": breached,
            "open_due_soon": due_soon,
            "operational_risk_score": _risk_score(breached=breached, due_soon=due_soon, hit_rate=hit_rate),
        }

    for row in scenarios:
        if baseline_scenario is None:
            row["delta_vs_current"] = None
            continue

        current_hit_rate = baseline_scenario["historical_hit_rate"]
        row["delta_vs_current"] = {
            "open_breaching": row["open_breaching"] - baseline_scenario["open_breaching"],
            "open_due_soon": row["open_due_soon"] - baseline_scenario["open_due_soon"],
            "historical_hit_rate": None
            if current_hit_rate is None or row["historical_hit_rate"] is None
            else round(row["historical_hit_rate"] - current_hit_rate, 1),
            "operational_risk_score": round(
                row["operational_risk_score"] - baseline_scenario["operational_risk_score"],
                1,
            ),
        }

    recommended_target_days = None
    if scenarios:
        recommended = min(
            scenarios,
            key=lambda row: (
                row["operational_risk_score"],
                -(row["historical_hit_rate"] or 0.0),
                abs(row["target_days"] - (current_target or row["target_days"])),
            ),
        )
        recommended_target_days = recommended["target_days"]
        for row in scenarios:
            row["is_recommended"] = row["target_days"] == recommended_target_days

    return {
        "scenarios": scenarios,
        "open_sample_size": len(open_ages),
        "historical_sample_size": len(lead_times),
        "current_target_days": current_target,
        "recommended_target_days": recommended_target_days,
    }
