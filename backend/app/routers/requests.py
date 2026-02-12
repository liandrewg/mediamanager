from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user
from app.database import get_db
from app.schemas import RequestCreate, RequestResponse, PaginatedResponse
from app.services import request_service

router = APIRouter()


@router.post("", response_model=RequestResponse)
async def create_request(
    body: RequestCreate,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        result = request_service.create_request(
            conn=db,
            user_id=user["user_id"],
            username=user["username"],
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
            title=body.title,
            poster_path=body.poster_path,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=PaginatedResponse)
async def get_my_requests(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    return request_service.get_user_requests(db, user["user_id"], status, page, limit)


@router.get("/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = request_service.get_request_by_id(db, request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")
    if result["user_id"] != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    return result


@router.delete("/{request_id}")
async def cancel_request(
    request_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        request_service.delete_request(db, request_id, user["user_id"])
        return {"message": "Request cancelled"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
