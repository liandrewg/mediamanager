from fastapi import APIRouter, Depends, HTTPException, Query
import httpx

from app.dependencies import get_current_user
from app.schemas import TMDBSearchResult, TMDBMovieDetail, TMDBTvDetail
from app.services.tmdb_client import tmdb_client
from app.services.request_service import get_request_for_tmdb
from app.database import get_db

router = APIRouter()


@router.get("/search")
async def search(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    type: str | None = Query(None, pattern="^(movie|tv)$"),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        if type == "movie":
            data = await tmdb_client.search_movies(query, page)
            results = [
                {**r, "media_type": "movie"} for r in data.get("results", [])
            ]
        elif type == "tv":
            data = await tmdb_client.search_tv(query, page)
            results = [{**r, "media_type": "tv"} for r in data.get("results", [])]
        else:
            data = await tmdb_client.search_multi(query, page)
            results = data.get("results", [])
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="TMDB API error")

    search_results = []
    for r in results:
        media_type = r.get("media_type", "movie")
        tmdb_id = r.get("id")
        title = r.get("title") or r.get("name", "")
        release_date = r.get("release_date") or r.get("first_air_date")

        existing_request = get_request_for_tmdb(db, tmdb_id, media_type, user["user_id"])

        search_results.append(TMDBSearchResult(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            overview=r.get("overview"),
            poster_path=r.get("poster_path"),
            release_date=release_date,
            vote_average=r.get("vote_average"),
            existing_request=existing_request,
        ))

    return {
        "results": search_results,
        "page": data.get("page", 1),
        "total_pages": data.get("total_pages", 1),
        "total_results": data.get("total_results", 0),
    }


@router.get("/movie/{tmdb_id}", response_model=TMDBMovieDetail)
async def get_movie(
    tmdb_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        data = await tmdb_client.get_movie_details(tmdb_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Movie not found")
        raise HTTPException(status_code=502, detail="TMDB API error")

    cast = [
        {"name": c.get("name"), "character": c.get("character"), "profile_path": c.get("profile_path")}
        for c in (data.get("credits", {}).get("cast", []))[:10]
    ]

    existing_request = get_request_for_tmdb(db, tmdb_id, "movie", user["user_id"])

    return TMDBMovieDetail(
        tmdb_id=data["id"],
        title=data.get("title", ""),
        overview=data.get("overview"),
        poster_path=data.get("poster_path"),
        backdrop_path=data.get("backdrop_path"),
        release_date=data.get("release_date"),
        runtime=data.get("runtime"),
        genres=[g["name"] for g in data.get("genres", [])],
        vote_average=data.get("vote_average"),
        vote_count=data.get("vote_count"),
        cast=cast,
        existing_request=existing_request,
    )


@router.get("/tv/{tmdb_id}", response_model=TMDBTvDetail)
async def get_tv_show(
    tmdb_id: int,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        data = await tmdb_client.get_tv_details(tmdb_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="TV show not found")
        raise HTTPException(status_code=502, detail="TMDB API error")

    cast = [
        {"name": c.get("name"), "character": c.get("character"), "profile_path": c.get("profile_path")}
        for c in (data.get("credits", {}).get("cast", []))[:10]
    ]

    existing_request = get_request_for_tmdb(db, tmdb_id, "tv", user["user_id"])

    return TMDBTvDetail(
        tmdb_id=data["id"],
        title=data.get("name", ""),
        overview=data.get("overview"),
        poster_path=data.get("poster_path"),
        backdrop_path=data.get("backdrop_path"),
        first_air_date=data.get("first_air_date"),
        number_of_seasons=data.get("number_of_seasons"),
        number_of_episodes=data.get("number_of_episodes"),
        genres=[g["name"] for g in data.get("genres", [])],
        vote_average=data.get("vote_average"),
        vote_count=data.get("vote_count"),
        cast=cast,
        existing_request=existing_request,
    )
