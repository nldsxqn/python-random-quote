"""Apply the Alembic revision to the configured SQLite file."""

from pathlib import Path


def alembic_ini() -> Path:
    return Path(__file__).resolve().parents[2] / "alembic.ini"


def upgrade_database(database_url: str) -> None:
    """Migrate a file database. In-memory URLs are left untouched."""
    if database_url.endswith(":memory:") or database_url in {"sqlite://", "sqlite:///:memory:"}:
        return
    from alembic import command
    from alembic.config import Config

    config = Config(str(alembic_ini()))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
