import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user, require_admin
from app.database import get_db
from app.schemas import BacklogCreate, BacklogResponse, BacklogUpdate

router = APIRouter()


# --- User endpoints ---

@router.post("", response_model=BacklogResponse)
async def create_report(
    body: BacklogCreate,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    if body.type not in ("bug", "feature"):
        raise HTTPException(status_code=400, detail="Type must be 'bug' or 'feature'")

    cursor = db.execute(
        """INSERT INTO backlog (user_id, username, type, title, description)
           VALUES (?, ?, ?, ?, ?)""",
        (user["user_id"], user["username"], body.type, body.title, body.description),
    )
    db.commit()
    row = db.execute("SELECT * FROM backlog WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@router.get("/mine")
async def get_my_reports(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rows = db.execute(
        "SELECT * FROM backlog WHERE user_id = ? ORDER BY created_at DESC",
        (user["user_id"],),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Admin endpoints ---

@router.get("")
async def get_all_backlog(
    status: str | None = Query(None),
    type: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(500, ge=1, le=500),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    where_parts = []
    params: list = []
    if status:
        where_parts.append("status = ?")
        params.append(status)
    if type:
        where_parts.append("type = ?")
        params.append(type)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    total = db.execute(f"SELECT COUNT(*) FROM backlog {where}", params).fetchone()[0]
    offset = (page - 1) * limit
    rows = db.execute(
        f"SELECT * FROM backlog {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
    }


@router.patch("/{item_id}", response_model=BacklogResponse)
async def update_backlog_item(
    item_id: int,
    body: BacklogUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    row = db.execute("SELECT * FROM backlog WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    valid_statuses = ("reported", "triaged", "in_progress", "ready_for_test", "resolved", "wont_fix")
    valid_priorities = ("low", "medium", "high", "critical")

    if body.status and body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid_statuses)}")
    if body.priority and body.priority not in valid_priorities:
        raise HTTPException(status_code=400, detail=f"Priority must be one of: {', '.join(valid_priorities)}")

    now = datetime.utcnow().isoformat()
    updates = []
    values = []

    if body.status is not None:
        updates.append("status = ?")
        values.append(body.status)
    if body.priority is not None:
        updates.append("priority = ?")
        values.append(body.priority)
    if body.admin_note is not None:
        updates.append("admin_note = ?")
        values.append(body.admin_note)

    if not updates:
        return dict(row)

    updates.append("updated_at = ?")
    values.append(now)
    values.append(item_id)

    db.execute(f"UPDATE backlog SET {', '.join(updates)} WHERE id = ?", values)
    db.commit()

    updated = db.execute("SELECT * FROM backlog WHERE id = ?", (item_id,)).fetchone()
    return dict(updated)


@router.delete("/{item_id}")
async def delete_backlog_item(
    item_id: int,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    row = db.execute("SELECT * FROM backlog WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    db.execute("DELETE FROM backlog WHERE id = ?", (item_id,))
    db.commit()
    return {"message": "Deleted"}


@router.get("/stats")
async def get_backlog_stats(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    status_rows = db.execute(
        "SELECT status, COUNT(*) as count FROM backlog GROUP BY status"
    ).fetchall()
    type_rows = db.execute(
        "SELECT type, COUNT(*) as count FROM backlog GROUP BY type"
    ).fetchall()

    by_status = {r["status"]: r["count"] for r in status_rows}
    by_type = {r["type"]: r["count"] for r in type_rows}
    total = sum(by_status.values())

    return {
        "total": total,
        "reported": by_status.get("reported", 0),
        "triaged": by_status.get("triaged", 0),
        "in_progress": by_status.get("in_progress", 0),
        "ready_for_test": by_status.get("ready_for_test", 0),
        "resolved": by_status.get("resolved", 0),
        "wont_fix": by_status.get("wont_fix", 0),
        "bugs": by_type.get("bug", 0),
        "features": by_type.get("feature", 0),
    }
