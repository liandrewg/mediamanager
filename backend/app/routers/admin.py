from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import require_admin
from app.database import get_db
from app.schemas import RequestUpdate, RequestResponse, PaginatedResponse
from app.services import request_service

router = APIRouter()


# --- Requests ---

@router.get("/requests", response_model=PaginatedResponse)
async def get_all_requests(
    status: str | None = Query(None),
    user_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=500),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_all_requests(db, status, user_id, page, limit)


@router.patch("/requests/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: int,
    body: RequestUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if body.status not in ("approved", "denied", "fulfilled", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")
    try:
        result = request_service.update_request_status(
            db, request_id, body.status, admin["user_id"], body.admin_note
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stats")
async def get_stats(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_request_stats(db)


# --- User Management ---

class RoleUpdate(BaseModel):
    role: str  # "admin" or "user"


@router.get("/users")
async def get_users(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    rows = db.execute(
        "SELECT user_id, username, role, granted_by, created_at, updated_at FROM user_roles ORDER BY username"
    ).fetchall()
    return [dict(r) for r in rows]


@router.patch("/users/{user_id}")
async def update_user_role(
    user_id: str,
    body: RoleUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")

    row = db.execute("SELECT * FROM user_roles WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent removing your own admin access
    if user_id == admin["user_id"] and body.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot remove your own admin access")

    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE user_roles SET role = ?, granted_by = ?, updated_at = ? WHERE user_id = ?",
        (body.role, admin["user_id"], now, user_id),
    )
    db.commit()

    updated = db.execute("SELECT user_id, username, role, granted_by, created_at, updated_at FROM user_roles WHERE user_id = ?", (user_id,)).fetchone()
    return dict(updated)
