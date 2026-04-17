from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import httpx

from app.dependencies import require_admin, get_current_user
from app.database import get_db
from app.schemas import (
    RequestUpdate,
    RequestResponse,
    PaginatedResponse,
    DuplicateGroupResponse,
    DuplicateMergeRequest,
    DuplicateMergeResponse,
)
from app.services import request_service
from app.services.jellyfin_client import jellyfin_client

router = APIRouter()


# --- Requests ---

@router.get("/requests", response_model=PaginatedResponse)
async def get_all_requests(
    status: str | None = Query(None),
    user_id: str | None = Query(None),
    media_type: str | None = Query(None, pattern="^(movie|tv|book)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=500),
    sort: str = Query("priority", pattern="^(priority|newest|oldest|supporters)$"),
    include_auto_closed_denied: bool = Query(False),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_all_requests(
        db,
        status,
        user_id,
        media_type,
        page,
        limit,
        sort,
        include_auto_closed_denied=include_auto_closed_denied,
    )


@router.get("/requests/duplicates", response_model=list[DuplicateGroupResponse])
async def list_duplicate_request_groups(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_duplicate_request_groups(db)


@router.post("/requests/duplicates/merge", response_model=DuplicateMergeResponse)
async def merge_duplicate_request_group(
    body: DuplicateMergeRequest,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    try:
        return request_service.merge_duplicate_requests(
            db,
            target_request_id=body.target_request_id,
            source_request_ids=body.source_request_ids,
            changed_by=admin["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/requests/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: int,
    body: RequestUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if body.status not in ("approved", "denied", "fulfilled", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")

    # When fulfilling, auto-search Jellyfin for a matching item
    jellyfin_item_id: str | None = None
    if body.status == "fulfilled":
        row = db.execute("SELECT title, media_type, jellyfin_item_id FROM requests WHERE id = ?", (request_id,)).fetchone()
        if row:
            # Only auto-link if not already linked
            if not row["jellyfin_item_id"] and row["media_type"] in ("movie", "tv"):
                try:
                    match = await jellyfin_client.search_item_by_title(
                        user_id=admin["user_id"],
                        token=admin["jellyfin_token"],
                        title=row["title"],
                        media_type=row["media_type"],
                    )
                    if match:
                        jellyfin_item_id = match["Id"]
                except Exception:
                    pass  # Non-fatal — fulfill without link
            else:
                jellyfin_item_id = row["jellyfin_item_id"]  # preserve existing

    try:
        result = request_service.update_request_status(
            db, request_id, body.status, admin["user_id"], body.admin_note,
            jellyfin_item_id=jellyfin_item_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class JellyfinLinkUpdate(BaseModel):
    jellyfin_item_id: str | None = None


class BulkRequestStatusUpdate(BaseModel):
    request_ids: list[int] = Field(..., min_length=1)
    status: str
    admin_note: str | None = None


class SlaPolicyUpdate(BaseModel):
    target_days: int = Field(..., ge=1, le=90)
    warning_days: int = Field(..., ge=0, le=30)


class SlaPolicyApplyRecommendedRequest(BaseModel):
    warning_days_override: int | None = Field(default=None, ge=0)


class SlaEscalationBulkRequest(BaseModel):
    request_ids: list[int] = Field(..., min_length=1)
    note: str | None = Field(default=None, max_length=500)


@router.post("/requests/bulk-status")
async def bulk_update_request_statuses(
    body: BulkRequestStatusUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if body.status not in ("approved", "denied", "fulfilled", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")

    result = request_service.bulk_update_request_status(
        db,
        request_ids=body.request_ids,
        new_status=body.status,
        changed_by=admin["user_id"],
        admin_note=body.admin_note,
    )
    return result


@router.patch("/requests/{request_id}/jellyfin-link", response_model=RequestResponse)
async def update_jellyfin_link(
    request_id: int,
    body: JellyfinLinkUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    """Manually set or clear the Jellyfin item ID for a fulfilled request."""
    row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    from datetime import datetime
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE requests SET jellyfin_item_id = ?, updated_at = ? WHERE id = ?",
        (body.jellyfin_item_id, now, request_id),
    )
    db.commit()
    return request_service.get_request_by_id(db, request_id)


@router.get("/stats")
async def get_stats(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_request_stats(db)


@router.get("/reply-pack")
async def get_reply_pack(
    limit: int = Query(8, ge=1, le=25),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_admin_reply_pack(db, limit=limit)


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


@router.get("/analytics")
async def get_analytics(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.services.analytics_service import get_analytics as _get_analytics

    policy = request_service.get_sla_policy(db)
    return _get_analytics(db, sla_days=policy["target_days"])


@router.get("/sla-policy")
async def get_sla_policy(
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_sla_policy(db)


@router.patch("/sla-policy")
async def patch_sla_policy(
    body: SlaPolicyUpdate,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if body.warning_days >= body.target_days:
        raise HTTPException(status_code=400, detail="warning_days must be less than target_days")
    return request_service.update_sla_policy(db, target_days=body.target_days, warning_days=body.warning_days)


@router.post("/sla-policy/apply-recommended")
async def apply_recommended_sla_policy(
    body: SlaPolicyApplyRecommendedRequest | None = None,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.services.analytics_service import get_analytics as _get_analytics

    current_policy = request_service.get_sla_policy(db)
    analytics = _get_analytics(db, sla_days=current_policy["target_days"])
    recommended_target = analytics.get("recommended_sla_days")

    if recommended_target is None:
        raise HTTPException(
            status_code=400,
            detail="No recommended SLA is available yet. Fulfill at least one request first.",
        )

    target_days = max(int(recommended_target), 1)
    if body is None or body.warning_days_override is None:
        warning_days = min(max(target_days - 2, 0), max(target_days - 1, 0))
    else:
        warning_days = body.warning_days_override

    return request_service.update_sla_policy(
        db,
        target_days=target_days,
        warning_days=warning_days,
    )


@router.get("/sla-policy/simulate")
async def simulate_sla_policy_targets(
    targets: str = Query("3,5,7,10,14"),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    from app.services.analytics_service import get_sla_target_simulation

    parsed_targets: list[int] = []
    for raw_target in targets.split(","):
        token = raw_target.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid SLA target: {token}")
        if value < 1 or value > 90:
            raise HTTPException(status_code=400, detail="SLA targets must be between 1 and 90 days")
        parsed_targets.append(value)

    if not parsed_targets:
        raise HTTPException(status_code=400, detail="At least one SLA target is required")

    policy = request_service.get_sla_policy(db)
    return get_sla_target_simulation(
        db,
        parsed_targets,
        current_target_days=policy["target_days"],
    )


@router.get("/sla-worklist")
async def get_sla_worklist(
    state: str = Query("all", pattern="^(all|breached|due_soon|on_track)$"),
    limit: int = Query(200, ge=1, le=1000),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.get_sla_worklist(db, state=state, limit=limit)


@router.post("/sla-worklist/escalate")
async def bulk_escalate_sla_worklist(
    body: SlaEscalationBulkRequest,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return request_service.bulk_escalate_sla_breaches(
        db,
        request_ids=body.request_ids,
        changed_by=admin["user_id"],
        note=body.note,
    )


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
