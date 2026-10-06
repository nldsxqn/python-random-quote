"""SQLite connectivity. Health is SELECT 1. Alembic creates the poker tables."""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    path_part = database_url[len(prefix) :]
    if path_part in {"", ":memory:"} or path_part.startswith("file:"):
        return
    database_path = Path(path_part)
    database_path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str) -> Engine:
    ensure_sqlite_directory(database_url)
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def database_status(engine: Engine) -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return "error"
    return "ok"
