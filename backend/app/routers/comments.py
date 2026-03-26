from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.database import get_db

router = APIRouter()


class CommentCreate(BaseModel):
    body: str


class CommentResponse(BaseModel):
    id: int
    request_id: int
    user_id: str
    username: str
    is_admin: bool
    body: str
    created_at: str


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "request_id": row["request_id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "body": row["body"],
        "created_at": row["created_at"],
    }


@router.get("/{request_id}/comments", response_model=list[CommentResponse])
async def get_comments(
    request_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get all comments for a request. Users can only see comments on their own requests."""
    row = db.execute(
        "SELECT user_id FROM requests WHERE id = ?", (request_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    # Non-admins can only view comments on their own requests
    if not user.get("is_admin") and row["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    comments = db.execute(
        "SELECT * FROM request_comments WHERE request_id = ? ORDER BY created_at ASC",
        (request_id,),
    ).fetchall()
    return [_row_to_dict(c) for c in comments]


@router.post("/{request_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    request_id: int,
    body: CommentCreate,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Add a comment to a request. Users can comment on their own requests; admins on any."""
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="Comment body cannot be empty")

    row = db.execute(
        "SELECT user_id FROM requests WHERE id = ?", (request_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    if not user.get("is_admin") and row["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.utcnow().isoformat()
    cursor = db.execute(
        """
        INSERT INTO request_comments (request_id, user_id, username, is_admin, body, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            user["user_id"],
            user["username"],
            1 if user.get("is_admin") else 0,
            body.body.strip(),
            now,
        ),
    )

    recipients = db.execute(
        "SELECT DISTINCT user_id FROM request_supporters WHERE request_id = ?",
        (request_id,),
    ).fetchall()
    for recipient in recipients:
        recipient_user_id = recipient["user_id"]
        if recipient_user_id == user["user_id"]:
            continue
        db.execute(
            """
            INSERT INTO request_notifications (request_id, user_id, type, message, actor_user_id, actor_name)
            VALUES (?, ?, 'comment_added', ?, ?, ?)
            """,
            (
                request_id,
                recipient_user_id,
                f"{user['username']} commented on this request.",
                user["user_id"],
                user["username"],
            ),
        )

    db.commit()
    comment = db.execute(
        "SELECT * FROM request_comments WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return _row_to_dict(comment)


@router.delete("/{request_id}/comments/{comment_id}", status_code=204)
async def delete_comment(
    request_id: int,
    comment_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete a comment. Users can delete their own; admins can delete any."""
    row = db.execute(
        "SELECT user_id FROM request_comments WHERE id = ? AND request_id = ?",
        (comment_id, request_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")

    if not user.get("is_admin") and row["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")

    db.execute("DELETE FROM request_comments WHERE id = ?", (comment_id,))
    db.commit()
