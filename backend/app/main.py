import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_db_connection
from app.routers import auth, tmdb, requests, jellyfin, admin
from app.services.jellyfin_client import jellyfin_client
from app.services.request_service import get_open_requests, auto_fulfill_request

logger = logging.getLogger(__name__)

LIBRARY_CHECK_INTERVAL = 300  # 5 minutes


async def check_library_for_fulfilled_requests():
    """Background task that checks if any open requests are now in the Jellyfin library."""
    while True:
        await asyncio.sleep(LIBRARY_CHECK_INTERVAL)
        try:
            conn = get_db_connection()
            open_requests = get_open_requests(conn)
            if not open_requests:
                conn.close()
                continue

            # We need a valid Jellyfin admin token to search the library.
            # Use the first request's user_id — but we don't have their token stored.
            # Instead, do a server-level search using the Jellyfin API key approach.
            # Since we proxy through user tokens, we'll check per-user on their next visit.
            # For the background task, we use a simple title search via the public API.
            for req in open_requests:
                try:
                    item_type = "Movie" if req["media_type"] == "movie" else "Series"
                    # Use Jellyfin's public items search (no auth needed for local server)
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{jellyfin_client.base_url}/Items",
                            params={
                                "SearchTerm": req["title"],
                                "IncludeItemTypes": item_type,
                                "Recursive": "true",
                                "Limit": 10,
                                "Fields": "ProviderIds",
                            },
                            headers={
                                "Authorization": jellyfin_client._auth_header(),
                            },
                        )
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
                    logger.debug("Error checking request #%d", req["id"])
                    continue

            conn.close()
        except Exception:
            logger.exception("Error in library check background task")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(check_library_for_fulfilled_requests())
    yield
    task.cancel()


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


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
