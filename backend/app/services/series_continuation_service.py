"""Series Continuation Radar.

Detects when previously-fulfilled TV shows have new seasons available on
TMDB that the household hasn't requested yet. Surfaces them to admins as
proactive add candidates so requesters don't have to DM "is season X out?".

Design intent:
- Admin time is scarce → one-click queue from a single radar panel.
- Every fulfilled TV request is implicit demand: when new content drops,
  the household almost certainly wants it.
- Snapshot the season count per fulfilled TV request so we know the
  baseline "what was there at fulfillment", then compare against current
  TMDB data to compute the delta.
- Anti-goal: do not duplicate a request that already exists for the same
  title (whether pending, approved, or already fulfilled for that delta).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

logger = logging.getLogger(__name__)


# How many days must pass between background refreshes for a single show.
RECHECK_INTERVAL_HOURS = 12


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def count_aired_seasons(details: dict) -> tuple[int, int, str | None]:
    """Return (total_seasons, aired_seasons, last_air_date) from a TMDB details payload.

    "aired_seasons" excludes season 0 (specials) and seasons whose air_date
    is in the future (announced but not yet released).
    """
    seasons = details.get("seasons") or []
    today = datetime.now(timezone.utc).date()

    total = 0
    aired = 0
    latest_air_date: str | None = None

    for s in seasons:
        season_number = s.get("season_number")
        if season_number is None or season_number <= 0:
            # Skip specials.
            continue

        episode_count = s.get("episode_count") or 0
        if episode_count <= 0:
            continue

        total += 1

        air_date_str = s.get("air_date")
        if not air_date_str:
            continue

        try:
            air_date = datetime.strptime(air_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        if air_date <= today:
            aired += 1
            if latest_air_date is None or air_date_str > latest_air_date:
                latest_air_date = air_date_str

    if total == 0:
        # Fallback to TMDB's claimed counts when no rich season data exists.
        total = int(details.get("number_of_seasons") or 0)
        aired = total
        latest_air_date = details.get("last_air_date")

    return total, aired, latest_air_date


def upsert_snapshot(
    conn: sqlite3.Connection,
    *,
    tmdb_id: int,
    title: str,
    poster_path: str | None,
    last_seen_seasons: int,
    last_aired_seasons: int,
    tmdb_status: str | None,
    last_air_date: str | None,
    fulfilled_at: str | None,
) -> None:
    """Insert or update a continuation snapshot row.

    Preserves existing dismissed_through unless the new aired count surpasses
    it (which means new seasons emerged after the last dismissal).
    """
    now = _utcnow_iso()
    existing = conn.execute(
        "SELECT dismissed_through, fulfilled_at FROM series_continuation_snapshots WHERE tmdb_id = ?",
        (tmdb_id,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO series_continuation_snapshots
                (tmdb_id, title, poster_path, last_seen_seasons, last_aired_seasons,
                 tmdb_status, last_air_date, fulfilled_at, checked_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tmdb_id,
                title,
                poster_path,
                last_seen_seasons,
                last_aired_seasons,
                tmdb_status,
                last_air_date,
                fulfilled_at,
                now,
                now,
                now,
            ),
        )
        return

    # Keep the earliest non-null fulfilled_at on file.
    fulfilled_to_store = existing["fulfilled_at"] or fulfilled_at

    conn.execute(
        """
        UPDATE series_continuation_snapshots
        SET title = ?,
            poster_path = ?,
            last_seen_seasons = ?,
            last_aired_seasons = ?,
            tmdb_status = ?,
            last_air_date = ?,
            fulfilled_at = ?,
            checked_at = ?,
            updated_at = ?
        WHERE tmdb_id = ?
        """,
        (
            title,
            poster_path,
            last_seen_seasons,
            last_aired_seasons,
            tmdb_status,
            last_air_date,
            fulfilled_to_store,
            now,
            now,
            tmdb_id,
        ),
    )


def get_fulfilled_tv_titles(conn: sqlite3.Connection) -> list[dict]:
    """Return the list of distinct fulfilled TV titles the household has.

    A title is "fulfilled" if at least one matching request was moved to
    'fulfilled' at some point. We pick the most recent fulfilled entry to
    establish the fulfilled_at baseline.
    """
    try:
        rows = conn.execute(
            """
            SELECT
                r.tmdb_id    AS tmdb_id,
                r.title      AS title,
                r.poster_path AS poster_path,
                MAX(rh.created_at) AS fulfilled_at
            FROM requests r
            JOIN request_history rh ON rh.request_id = r.id
            WHERE r.media_type = 'tv'
              AND rh.new_status = 'fulfilled'
            GROUP BY r.tmdb_id
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "title": row["title"],
            "poster_path": row["poster_path"],
            "fulfilled_at": row["fulfilled_at"],
        }
        for row in rows
    ]


def get_open_tmdb_ids_for_tv(conn: sqlite3.Connection) -> set[int]:
    """tmdb_ids of TV titles with currently-open (pending/approved) requests."""
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT tmdb_id FROM requests
            WHERE media_type = 'tv'
              AND status IN ('pending', 'approved')
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {row["tmdb_id"] for row in rows}


def list_radar_candidates(conn: sqlite3.Connection) -> list[dict]:
    """Return the current radar of TV shows with new seasons available.

    A show appears on the radar when:
      - A fulfilled request exists for it AND
      - The TMDB-aired season count exceeds dismissed_through AND
      - No open follow-up request already exists for the title.
    """
    open_ids = get_open_tmdb_ids_for_tv(conn)

    try:
        rows = conn.execute(
            """
            SELECT s.*
            FROM series_continuation_snapshots s
            WHERE s.last_aired_seasons > s.dismissed_through
            ORDER BY (s.last_aired_seasons - s.dismissed_through) DESC,
                     s.last_air_date DESC,
                     s.title ASC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    candidates: list[dict] = []
    for row in rows:
        if row["tmdb_id"] in open_ids:
            # Already in the active queue, skip.
            continue
        delta = max(0, row["last_aired_seasons"] - row["dismissed_through"])
        candidates.append(
            {
                "tmdb_id": row["tmdb_id"],
                "title": row["title"],
                "poster_path": row["poster_path"],
                "last_seen_seasons": row["last_seen_seasons"],
                "last_aired_seasons": row["last_aired_seasons"],
                "dismissed_through": row["dismissed_through"],
                "new_seasons": delta,
                "tmdb_status": row["tmdb_status"],
                "last_air_date": row["last_air_date"],
                "fulfilled_at": row["fulfilled_at"],
                "checked_at": row["checked_at"],
            }
        )
    return candidates


def queue_continuation(
    conn: sqlite3.Connection,
    *,
    tmdb_id: int,
    admin_user_id: str,
    admin_username: str,
) -> dict:
    """Create an approved follow-up request for a continuation candidate.

    Returns the created request row plus the snapshot delta that was
    queued. Marks dismissed_through to the queued aired-season count so
    the same show doesn't keep appearing on the radar.
    """
    snap = conn.execute(
        "SELECT * FROM series_continuation_snapshots WHERE tmdb_id = ?",
        (tmdb_id,),
    ).fetchone()
    if snap is None:
        raise ValueError("No continuation snapshot for this title")

    if snap["last_aired_seasons"] <= snap["dismissed_through"]:
        raise ValueError("No new seasons to queue for this title")

    # Make sure no open follow-up already exists.
    existing_open = conn.execute(
        """
        SELECT id, status FROM requests
        WHERE tmdb_id = ? AND media_type = 'tv'
          AND status IN ('pending', 'approved')
        LIMIT 1
        """,
        (tmdb_id,),
    ).fetchone()
    if existing_open:
        raise ValueError(
            f"An open '{existing_open['status']}' request already exists for this title"
        )

    new_seasons = snap["last_aired_seasons"] - snap["dismissed_through"]
    note = (
        f"Continuation follow-up: {new_seasons} new season"
        f"{'s' if new_seasons != 1 else ''} aired since previous fulfillment "
        f"(now {snap['last_aired_seasons']} aired total)."
    )

    cursor = conn.execute(
        """
        INSERT INTO requests
            (user_id, username, tmdb_id, media_type, title, poster_path,
             status, admin_note)
        VALUES (?, ?, ?, 'tv', ?, ?, 'approved', ?)
        """,
        (
            admin_user_id,
            admin_username,
            tmdb_id,
            snap["title"],
            snap["poster_path"],
            note,
        ),
    )
    request_id = cursor.lastrowid

    # Track the admin as the supporter so existing flows behave correctly.
    conn.execute(
        "INSERT INTO request_supporters (request_id, user_id, username) VALUES (?, ?, ?)",
        (request_id, admin_user_id, admin_username),
    )

    # Record the lifecycle entry: pending → approved (skipping the pending step).
    conn.execute(
        """
        INSERT INTO request_history (request_id, old_status, new_status, changed_by, note)
        VALUES (?, 'pending', 'approved', ?, ?)
        """,
        (request_id, admin_user_id, "Auto-queued from continuation radar"),
    )

    # Bump dismissed_through so the radar won't keep flagging the same delta.
    now = _utcnow_iso()
    conn.execute(
        """
        UPDATE series_continuation_snapshots
        SET dismissed_through = ?,
            dismissed_at = ?,
            dismissed_by = ?,
            updated_at = ?
        WHERE tmdb_id = ?
        """,
        (snap["last_aired_seasons"], now, admin_user_id, now, tmdb_id),
    )

    conn.commit()

    return {
        "request_id": request_id,
        "tmdb_id": tmdb_id,
        "title": snap["title"],
        "queued_through_seasons": snap["last_aired_seasons"],
        "new_seasons": new_seasons,
        "admin_note": note,
    }


def dismiss_continuation(
    conn: sqlite3.Connection,
    *,
    tmdb_id: int,
    admin_user_id: str,
    through_seasons: int | None = None,
) -> dict:
    """Dismiss a continuation candidate.

    If through_seasons is None, dismiss through the currently-aired count.
    """
    snap = conn.execute(
        "SELECT * FROM series_continuation_snapshots WHERE tmdb_id = ?",
        (tmdb_id,),
    ).fetchone()
    if snap is None:
        raise ValueError("No continuation snapshot for this title")

    target = through_seasons if through_seasons is not None else snap["last_aired_seasons"]
    if target < snap["dismissed_through"]:
        target = snap["dismissed_through"]
    target = min(target, snap["last_aired_seasons"])

    now = _utcnow_iso()
    conn.execute(
        """
        UPDATE series_continuation_snapshots
        SET dismissed_through = ?,
            dismissed_at = ?,
            dismissed_by = ?,
            updated_at = ?
        WHERE tmdb_id = ?
        """,
        (target, now, admin_user_id, now, tmdb_id),
    )
    conn.commit()
    return {
        "tmdb_id": tmdb_id,
        "title": snap["title"],
        "dismissed_through": target,
    }


def update_snapshot_from_tmdb(
    conn: sqlite3.Connection,
    *,
    tmdb_id: int,
    fulfilled_at: str | None,
    title_fallback: str,
    poster_fallback: str | None,
    tmdb_details: dict,
) -> dict:
    """Take a fresh TMDB details payload for a TV show and update its snapshot.

    Returns the post-update snapshot row as a dict.
    """
    total, aired, last_air = count_aired_seasons(tmdb_details)
    title = tmdb_details.get("name") or title_fallback
    poster = tmdb_details.get("poster_path") or poster_fallback
    status = tmdb_details.get("status")

    # Initial baseline: when we first record a fulfilled show and we have no
    # prior dismissed_through, set it to the season count at fulfillment so
    # only NEW seasons after that point appear on the radar.
    existing = conn.execute(
        "SELECT dismissed_through FROM series_continuation_snapshots WHERE tmdb_id = ?",
        (tmdb_id,),
    ).fetchone()

    upsert_snapshot(
        conn,
        tmdb_id=tmdb_id,
        title=title,
        poster_path=poster,
        last_seen_seasons=total,
        last_aired_seasons=aired,
        tmdb_status=status,
        last_air_date=last_air,
        fulfilled_at=fulfilled_at,
    )

    if existing is None:
        # First time we've seen this fulfilled show: baseline dismissed_through
        # to the currently-aired season count, so the radar only flags
        # genuinely new seasons going forward.
        conn.execute(
            "UPDATE series_continuation_snapshots SET dismissed_through = ? WHERE tmdb_id = ?",
            (aired, tmdb_id),
        )

    conn.commit()
    refreshed = conn.execute(
        "SELECT * FROM series_continuation_snapshots WHERE tmdb_id = ?",
        (tmdb_id,),
    ).fetchone()
    return dict(refreshed)


async def refresh_radar(
    conn: sqlite3.Connection,
    tmdb_fetch,
    *,
    only_stale: bool = True,
) -> dict:
    """Refresh continuation snapshots for every fulfilled TV title.

    `tmdb_fetch` is an async callable that takes a tmdb_id and returns a
    TMDB tv details dict. Decoupling lets us inject a stub in tests and a
    real client in production.
    """
    fulfilled = get_fulfilled_tv_titles(conn)
    if not fulfilled:
        return {"checked": 0, "errors": 0, "candidates": 0}

    cutoff = datetime.now(timezone.utc).timestamp() - (RECHECK_INTERVAL_HOURS * 3600)

    checked = 0
    errors = 0

    for entry in fulfilled:
        tmdb_id = entry["tmdb_id"]
        existing = conn.execute(
            "SELECT checked_at FROM series_continuation_snapshots WHERE tmdb_id = ?",
            (tmdb_id,),
        ).fetchone()

        if only_stale and existing and existing["checked_at"]:
            last_checked = _parse_iso(existing["checked_at"])
            if last_checked and last_checked.timestamp() > cutoff:
                continue

        try:
            details = await tmdb_fetch(tmdb_id)
        except Exception as exc:  # noqa: BLE001 - we want to keep iterating
            errors += 1
            logger.warning("continuation radar: TMDB fetch failed for %s: %s", tmdb_id, exc)
            continue

        update_snapshot_from_tmdb(
            conn,
            tmdb_id=tmdb_id,
            fulfilled_at=entry["fulfilled_at"],
            title_fallback=entry["title"],
            poster_fallback=entry["poster_path"],
            tmdb_details=details,
        )
        checked += 1

    candidates = list_radar_candidates(conn)
    return {
        "checked": checked,
        "errors": errors,
        "candidates": len(candidates),
    }
