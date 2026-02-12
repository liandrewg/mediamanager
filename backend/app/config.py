from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jellyfin_url: str = "http://localhost:8096"
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    secret_key: str = "change-me"
    database_url: str = "sqlite:///./mediamanager.db"
    cors_origins: str = "http://localhost:5173"
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
