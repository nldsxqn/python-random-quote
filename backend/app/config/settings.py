from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_url() -> str:
    """SQLite file at <repo>/data/openpokerlab.db for a source checkout."""
    repo_root = Path(__file__).resolve().parents[3]
    database_path = repo_root / "data" / "openpokerlab.db"
    return f"sqlite:///{database_path.as_posix()}"


def default_cors_origins() -> list[str]:
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


# Localhost, loopback, RFC1918, link-local, a single-label PC name, or a .local name.
# This is not a wildcard: public hosts such as https://evil.example do not match.
LAN_ORIGIN_REGEX = (
    r"(?i)^https?://"
    r"(?:"
    r"localhost"
    r"|127(?:\.\d{1,3}){3}"
    r"|\[::1\]"
    r"|10(?:\.\d{1,3}){3}"
    r"|192\.168(?:\.\d{1,3}){2}"
    r"|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}"
    r"|169\.254(?:\.\d{1,3}){2}"
    r"|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+local"
    r")"
    r"(?::\d{1,5})?"
    r"$"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = Field(default_factory=default_database_url)
    cors_origins: list[str] = Field(default_factory=default_cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
