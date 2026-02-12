import httpx

from app.config import settings


class JellyfinClient:
    def __init__(self):
        self.base_url = settings.jellyfin_url.rstrip("/")
        self.client_name = "MediaManager"
        self.client_version = "1.0.0"
        self.device_name = "MediaManager-Server"
        self.device_id = "mediamanager-backend-001"

    def _auth_header(self, token: str | None = None) -> str:
        header = (
            f'MediaBrowser Client="{self.client_name}", '
            f'Device="{self.device_name}", '
            f'DeviceId="{self.device_id}", '
            f'Version="{self.client_version}"'
        )
        if token:
            header += f', Token="{token}"'
        return header

    async def authenticate(self, username: str, password: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/Users/AuthenticateByName",
                json={"Username": username, "Pw": password},
                headers={
                    "Authorization": self._auth_header(),
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_views(self, user_id: str, token: str) -> list:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/Users/{user_id}/Views",
                headers={"Authorization": self._auth_header(token)},
            )
            resp.raise_for_status()
            return resp.json().get("Items", [])

    async def get_items(
        self,
        user_id: str,
        token: str,
        include_item_types: str = "Movie",
        search_term: str | None = None,
        start_index: int = 0,
        limit: int = 50,
        sort_by: str = "SortName",
        sort_order: str = "Ascending",
        parent_id: str | None = None,
    ) -> dict:
        params = {
            "IncludeItemTypes": include_item_types,
            "Recursive": "true",
            "StartIndex": start_index,
            "Limit": limit,
            "SortBy": sort_by,
            "SortOrder": sort_order,
            "Fields": "Overview,Genres,CommunityRating,ProductionYear,ProviderIds",
            "ImageTypeLimit": 1,
            "EnableImageTypes": "Primary,Backdrop",
        }
        if search_term:
            params["SearchTerm"] = search_term
        if parent_id:
            params["ParentId"] = parent_id

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/Users/{user_id}/Items",
                params=params,
                headers={"Authorization": self._auth_header(token)},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_latest_items(self, user_id: str, token: str, limit: int = 20) -> list:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/Users/{user_id}/Items/Latest",
                params={"Limit": limit, "Fields": "Overview,ProductionYear,ProviderIds"},
                headers={"Authorization": self._auth_header(token)},
            )
            resp.raise_for_status()
            return resp.json()

    def get_image_url(self, item_id: str, image_type: str = "Primary") -> str:
        return f"{self.base_url}/Items/{item_id}/Images/{image_type}"


jellyfin_client = JellyfinClient()
