import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_db_connection
from app.routers import auth, tmdb, requests, jellyfin, admin, backlog, tunnel, books, comments
from app.services.jellyfin_client import jellyfin_client
from app.services.request_service import (
    get_open_requests,
    auto_fulfill_request,
    run_request_lifecycle_rules,
)

logger = logging.getLogger(__name__)

LIBRARY_CHECK_INTERVAL = 300  # 5 minutes
REQUEST_ESCALATION_INTERVAL = 86400  # daily


async def check_library_for_fulfilled_requests():
    """Background task that checks if any open requests are now in the Jellyfin library."""
    import httpx

    while True:
        await asyncio.sleep(LIBRARY_CHECK_INTERVAL)
        try:
            conn = get_db_connection()
            open_requests = get_open_requests(conn)
            if not open_requests:
                conn.close()
                continue

            # Get a valid Jellyfin token from the most recently active admin
            admin_row = conn.execute(
                "SELECT user_id, jellyfin_token FROM user_roles WHERE role = 'admin' AND jellyfin_token IS NOT NULL AND jellyfin_token != '' LIMIT 1"
            ).fetchone()

            if not admin_row or not admin_row["jellyfin_token"]:
                logger.debug("No admin Jellyfin token available for auto-fulfill check")
                conn.close()
                continue

            admin_token = admin_row["jellyfin_token"]
            admin_user_id = admin_row["user_id"]

            for req in open_requests:
                if req["media_type"] == "book":
                    continue
                try:
                    item_type = "Movie" if req["media_type"] == "movie" else "Series"
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{jellyfin_client.base_url}/Users/{admin_user_id}/Items",
                            params={
                                "SearchTerm": req["title"],
                                "IncludeItemTypes": item_type,
                                "Recursive": "true",
                                "Limit": 10,
                                "Fields": "ProviderIds",
                            },
                            headers={
                                "Authorization": jellyfin_client._auth_header(admin_token),
                            },
                        )
                        if resp.status_code == 401:
                            logger.warning("Admin Jellyfin token expired for auto-fulfill")
                            break
                        if resp.status_code != 200:
                            continue
                        data = resp.json()

                    for item in data.get("Items", []):
                        provider_ids = item.get("ProviderIds", {})
                        if str(provider_ids.get("Tmdb", "")) == str(req["tmdb_id"]):
                            logger.info(
                                "Auto-fulfilling request #%d (%s) - found in library",
                                req["id"], req["title"],
                            )
                            auto_fulfill_request(conn, req["id"])
                            break
                except Exception:
                    logger.debug("Error checking request #%d", req["id"], exc_info=True)
                    continue

            conn.close()
        except Exception:
            logger.exception("Error in library check background task")


async def run_daily_request_lifecycle():
    """Daily lifecycle automation for request queue maintenance rules."""
    while True:
        try:
            conn = get_db_connection()
            result = run_request_lifecycle_rules(conn)
            if any(result.values()):
                logger.info(
                    "Lifecycle rules applied: escalated=%d reminded=%d auto_closed_denied=%d",
                    result["escalated"],
                    result["reminded"],
                    result["auto_closed_denied"],
                )
            conn.close()
        except Exception:
            logger.exception("Error in request lifecycle automation task")

        await asyncio.sleep(REQUEST_ESCALATION_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    library_task = asyncio.create_task(check_library_for_fulfilled_requests())
    lifecycle_task = asyncio.create_task(run_daily_request_lifecycle())
    yield
    library_task.cancel()
    lifecycle_task.cancel()


app = FastAPI(title="Media Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tmdb.router, prefix="/api/tmdb", tags=["tmdb"])
app.include_router(requests.router, prefix="/api/requests", tags=["requests"])
app.include_router(jellyfin.router, prefix="/api/library", tags=["library"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(backlog.router, prefix="/api/backlog", tags=["backlog"])
app.include_router(tunnel.router, prefix="/api/admin/tunnel", tags=["tunnel"])
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(comments.router, prefix="/api/requests", tags=["comments"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
