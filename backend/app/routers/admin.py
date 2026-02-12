from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import require_admin
from app.database import get_db
from app.schemas import RequestUpdate, RequestResponse, PaginatedResponse
from app.services import request_service

router = APIRouter()


@router.get("/requests", response_model=PaginatedResponse)
async def get_all_requests(
    status: str | None = Query(None),
    user_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
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
