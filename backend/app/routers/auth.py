from fastapi import APIRouter, HTTPException, Depends
import jwt
import httpx

from app.config import settings
from app.schemas import LoginRequest, LoginResponse, UserInfo
from app.dependencies import get_current_user
from app.services.jellyfin_client import jellyfin_client

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    try:
        result = await jellyfin_client.authenticate(body.username, body.password)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        raise HTTPException(status_code=502, detail="Jellyfin server error")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to Jellyfin server")

    user_data = result.get("User", {})
    access_token = result.get("AccessToken", "")

    payload = {
        "user_id": user_data.get("Id", ""),
        "username": user_data.get("Name", ""),
        "is_admin": user_data.get("Policy", {}).get("IsAdministrator", False),
        "jellyfin_token": access_token,
    }

    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")

    return LoginResponse(
        token=token,
        user=UserInfo(
            id=payload["user_id"],
            username=payload["username"],
            is_admin=payload["is_admin"],
        ),
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: dict = Depends(get_current_user)):
    return UserInfo(
        id=user["user_id"],
        username=user["username"],
        is_admin=user["is_admin"],
    )


@router.post("/logout")
async def logout():
    return {"message": "Logged out"}
