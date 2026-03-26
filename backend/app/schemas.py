from pydantic import BaseModel, Field
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
    supporter_count: int = 1
    supporters: list[str] = []
    is_owner: bool = False
    user_supporting: bool = False
    days_open: int = 0
    priority_score: float = 0
    jellyfin_item_id: Optional[str] = None
    watch_url: Optional[str] = None
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


class DuplicateGroupResponse(BaseModel):
    group_id: str
    media_type: str
    normalized_title: str
    matched_by_title: bool
    matched_by_tmdb: bool
    shared_tmdb_ids: list[int] = []
    request_ids: list[int] = []
    total_supporters: int
    requests: list[RequestResponse] = []


class DuplicateMergeRequest(BaseModel):
    target_request_id: int
    source_request_ids: list[int] = Field(..., min_length=1)


class DuplicateMergeResponse(BaseModel):
    target: RequestResponse
    merged_source_ids: list[int] = []
    notifications_created: int


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
    community_request_id: Optional[int] = None
    community_request_status: Optional[str] = None
    community_supporters: int = 0
    user_supporting: bool = False


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
    community_request_id: Optional[int] = None
    community_request_status: Optional[str] = None
    community_supporters: int = 0
    user_supporting: bool = False


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


# --- Books (Open Library) ---
class BookSearchResult(BaseModel):
    ol_work_id: int
    ol_work_key: str
    media_type: str = "book"
    title: str
    authors: list[str] = []
    first_publish_year: Optional[int] = None
    cover_url: Optional[str] = None
    subject: list[str] = []
    edition_count: Optional[int] = None
    ratings_average: Optional[float] = None
    existing_request: Optional[str] = None
    already_in_library: bool = False


class BookDetail(BaseModel):
    ol_work_id: int
    ol_work_key: str
    title: str
    authors: list[str] = []
    description: Optional[str] = None
    first_publish_year: Optional[int] = None
    cover_url: Optional[str] = None
    subjects: list[str] = []
    page_count: Optional[int] = None
    edition_count: Optional[int] = None
    ratings_average: Optional[float] = None
    existing_request: Optional[str] = None
    already_in_library: bool = False


# --- Backlog ---
class BacklogCreate(BaseModel):
    type: str = "bug"
    title: str
    description: Optional[str] = None

class BacklogResponse(BaseModel):
    id: int
    user_id: str
    username: str
    type: str
    title: str
    description: Optional[str]
    status: str
    priority: str
    admin_note: Optional[str]
    created_at: str
    updated_at: str

class BacklogUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    admin_note: Optional[str] = None
