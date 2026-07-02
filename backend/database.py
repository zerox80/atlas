import os
from typing import Any

from sqlmodel import SQLModel, create_engine, Session

sqlite_url = os.getenv("DATABASE_URL", "sqlite:///./data/ze_dashboard.db")
debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"

engine_kwargs: dict[str, Any] = {"echo": debug_mode}
if sqlite_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(sqlite_url, **engine_kwargs)


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
