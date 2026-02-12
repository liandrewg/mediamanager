from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: str
    username: str
    is_admin: bool


class LoginResponse(BaseModel):
    token: str
    user: UserInfo


# --- Requests ---
class RequestCreate(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    poster_path: Optional[str] = None


class RequestResponse(BaseModel):
    id: int
    user_id: str
    username: str
    tmdb_id: int
    media_type: str
    title: str
    poster_path: Optional[str]
    status: str
    admin_note: Optional[str]
    created_at: str
    updated_at: str


class RequestUpdate(BaseModel):
    status: str
    admin_note: Optional[str] = None


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    limit: int
    total_pages: int


# --- TMDB ---
class TMDBSearchResult(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    release_date: Optional[str] = None
    vote_average: Optional[float] = None
    already_in_library: bool = False
    existing_request: Optional[str] = None


class TMDBMovieDetail(BaseModel):
    tmdb_id: int
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    release_date: Optional[str] = None
    runtime: Optional[int] = None
    genres: list[str] = []
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    cast: list[dict] = []
    already_in_library: bool = False
    existing_request: Optional[str] = None


class TMDBTvDetail(BaseModel):
    tmdb_id: int
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    first_air_date: Optional[str] = None
    number_of_seasons: Optional[int] = None
    number_of_episodes: Optional[int] = None
    genres: list[str] = []
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    cast: list[dict] = []
    already_in_library: bool = False
    existing_request: Optional[str] = None


# --- Library ---
class LibraryItem(BaseModel):
    jellyfin_id: str
    title: str
    year: Optional[int] = None
    poster_url: Optional[str] = None
    media_type: str


class LibraryStats(BaseModel):
    total_movies: int
    total_shows: int
    total_episodes: int
