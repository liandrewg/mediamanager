from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import httpx

from app.dependencies import require_admin
from app.database import get_db
from app.schemas import RequestUpdate, RequestResponse, PaginatedResponse
from app.services import request_service
from app.services.jellyfin_client import jellyfin_client

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


# --- Health Check ---

@router.get("/health")
async def health_check(admin: dict = Depends(require_admin)):
    checks = {}

    # Jellyfin
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{jellyfin_client.base_url}/System/Info/Public",
            )
            if resp.status_code == 200:
                info = resp.json()
                checks["jellyfin"] = {
                    "status": "ok",
                    "url": jellyfin_client.base_url,
                    "server_name": info.get("ServerName"),
                    "version": info.get("Version"),
                }
            else:
                checks["jellyfin"] = {
                    "status": "error",
                    "url": jellyfin_client.base_url,
                    "detail": f"HTTP {resp.status_code}",
                }
    except Exception as e:
        checks["jellyfin"] = {
            "status": "error",
            "url": jellyfin_client.base_url,
            "detail": str(e),
        }

    # TMDB
    try:
        from app.config import settings
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.tmdb_base_url}/configuration",
                params={"api_key": settings.tmdb_api_key},
            )
            checks["tmdb"] = {
                "status": "ok" if resp.status_code == 200 else "error",
                "detail": None if resp.status_code == 200 else f"HTTP {resp.status_code}",
            }
    except Exception as e:
        checks["tmdb"] = {"status": "error", "detail": str(e)}

    # Database
    try:
        from app.database import get_db_connection
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "detail": str(e)}

    return checks


@router.post("/jellyfin/scan")
async def trigger_jellyfin_scan(admin: dict = Depends(require_admin)):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{jellyfin_client.base_url}/Library/Refresh",
                headers={
                    "Authorization": jellyfin_client._auth_header(admin["jellyfin_token"]),
                },
            )
            if resp.status_code == 204:
                return {"status": "ok", "message": "Library scan started"}
            elif resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Jellyfin session expired. Please log out and log back in.")
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"Jellyfin returned {resp.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to Jellyfin server")
