from fastapi import APIRouter, HTTPException, Depends
import jwt
import httpx

from app.config import settings
from app.schemas import LoginRequest, LoginResponse, UserInfo
from app.dependencies import get_current_user
from app.database import get_db
from app.services.jellyfin_client import jellyfin_client

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db=Depends(get_db)):
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
    user_id = user_data.get("Id", "")
    username = user_data.get("Name", "")
    jellyfin_admin = user_data.get("Policy", {}).get("IsAdministrator", False)

    # Check app-level role (Jellyfin admin always gets admin access)
    app_role = db.execute(
        "SELECT role FROM user_roles WHERE user_id = ?", (user_id,)
    ).fetchone()
    is_admin = jellyfin_admin or (app_role and app_role["role"] == "admin")

    # Upsert user into user_roles table so we track all users who have logged in
    existing = db.execute("SELECT user_id FROM user_roles WHERE user_id = ?", (user_id,)).fetchone()
    if not existing:
        role = "admin" if jellyfin_admin else "user"
        db.execute(
            "INSERT INTO user_roles (user_id, username, role) VALUES (?, ?, ?)",
            (user_id, username, role),
        )
        db.commit()
    else:
        # Keep username in sync
        db.execute("UPDATE user_roles SET username = ? WHERE user_id = ?", (username, user_id))
        db.commit()

    payload = {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
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
