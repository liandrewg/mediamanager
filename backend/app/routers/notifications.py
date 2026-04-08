from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter()


class NotificationResponse(BaseModel):
    id: int
    request_id: int
    user_id: str
    type: str
    message: str
    actor_user_id: str | None = None
    actor_name: str | None = None
    is_read: bool
    created_at: str


class NotificationSummaryResponse(BaseModel):
    total: int
    unread: int
    by_type: dict[str, int]


@router.get("/summary", response_model=NotificationSummaryResponse)
async def get_notification_summary(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rows = db.execute(
        """
        SELECT type, COUNT(*) as total, SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) as unread
        FROM request_notifications
        WHERE user_id = ?
        GROUP BY type
        """,
        (user["user_id"],),
    ).fetchall()

    by_type: dict[str, int] = {}
    total = 0
    unread = 0
    for row in rows:
        row_total = int(row["total"] or 0)
        row_unread = int(row["unread"] or 0)
        by_type[row["type"]] = row_unread
        total += row_total
        unread += row_unread

    return {
        "total": total,
        "unread": unread,
        "by_type": by_type,
    }


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rows = db.execute(
        """
        SELECT id, request_id, user_id, type, message, actor_user_id, actor_name, is_read, created_at
        FROM request_notifications
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (user["user_id"],),
    ).fetchall()
    return [
        {
            **dict(row),
            "is_read": bool(row["is_read"]),
        }
        for row in rows
    ]


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    row = db.execute(
        "SELECT id FROM request_notifications WHERE id = ? AND user_id = ?",
        (notification_id, user["user_id"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.execute(
        "UPDATE request_notifications SET is_read = 1 WHERE id = ?",
        (notification_id,),
    )
    db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_notifications_read(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.execute(
        "UPDATE request_notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
        (user["user_id"],),
    )
    db.commit()
    return {"ok": True, "updated": cursor.rowcount}
