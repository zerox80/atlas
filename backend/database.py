import os
from typing import Any

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine, Session

sqlite_url = os.getenv("DATABASE_URL", "sqlite:///./data/ze_dashboard.db")
debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
IS_SQLITE = sqlite_url.startswith("sqlite")

engine_kwargs: dict[str, Any] = {"echo": debug_mode}
if IS_SQLITE:
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 30,
    }

engine = create_engine(sqlite_url, **engine_kwargs)


def _unicode_casefold(value: object) -> str:
    """Return a Unicode-aware search key for SQLite text comparisons."""
    return value.casefold() if isinstance(value, str) else ""


def _configure_sqlite_connection(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    dbapi_connection.create_function(
        "unicode_casefold",
        1,
        _unicode_casefold,
        deterministic=True,
    )
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


if IS_SQLITE:
    event.listen(engine, "connect", _configure_sqlite_connection)


def ensure_sqlite_directory() -> None:
    if not sqlite_url.startswith("sqlite:///") or sqlite_url == "sqlite:///:memory:":
        return

    db_path = sqlite_url.replace("sqlite:///", "", 1)
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def create_db_and_tables():
    ensure_sqlite_directory()
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
