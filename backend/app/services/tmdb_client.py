import httpx

from app.config import settings


class TMDBClient:
    def __init__(self):
        self.base_url = settings.tmdb_base_url.rstrip("/")
        self.api_key = settings.tmdb_api_key

    def _params(self, extra: dict | None = None) -> dict:
        params = {"api_key": self.api_key}
        if extra:
            params.update(extra)
        return params

    async def search_multi(self, query: str, page: int = 1) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/search/multi",
                params=self._params({"query": query, "page": page}),
            )
            resp.raise_for_status()
            data = resp.json()
            # Filter to only movie and tv results
            data["results"] = [
                r for r in data.get("results", [])
                if r.get("media_type") in ("movie", "tv")
            ]
            return data

    async def search_movies(self, query: str, page: int = 1) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/search/movie",
                params=self._params({"query": query, "page": page}),
            )
            resp.raise_for_status()
            return resp.json()

    async def search_tv(self, query: str, page: int = 1) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/search/tv",
                params=self._params({"query": query, "page": page}),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_movie_details(self, tmdb_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/movie/{tmdb_id}",
                params=self._params({"append_to_response": "credits"}),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_tv_details(self, tmdb_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/tv/{tmdb_id}",
                params=self._params({"append_to_response": "credits"}),
            )
            resp.raise_for_status()
            return resp.json()


tmdb_client = TMDBClient()
