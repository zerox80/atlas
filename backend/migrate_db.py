import os
import sqlite3
from typing import Iterable


def get_default_db_path() -> str:
    db_url = os.getenv("DATABASE_URL", "sqlite:///./data/ze_dashboard.db")
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "", 1)
    return "data/ze_dashboard.db"


DB_PATH = get_default_db_path()


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def existing_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {info[1] for info in cursor.fetchall()}


def add_missing_columns(
    cursor: sqlite3.Cursor,
    table_name: str,
    column_definitions: Iterable[tuple[str, str]],
) -> None:
    if not table_exists(cursor, table_name):
        return

    columns = existing_columns(cursor, table_name)
    for column_name, definition in column_definitions:
        if column_name in columns:
            print(f"Column '{table_name}.{column_name}' already exists.")
            continue
        print(f"Adding column '{table_name}.{column_name}'...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def ensure_unique_permission_index(cursor: sqlite3.Cursor) -> None:
    if not table_exists(cursor, "contractpermission"):
        return

    cursor.execute(
        """
        DELETE FROM contractpermission
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM contractpermission
            GROUP BY user_id, contract_id
        )
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        ix_contractpermission_user_contract
        ON contractpermission (user_id, contract_id)
        """
    )


def migrate(db_path: str | None = None) -> None:
    resolved_db_path = db_path or DB_PATH
    print(f"Connecting to database at {resolved_db_path}...")

    if not os.path.exists(resolved_db_path):
        print("Database file not found. Skipping migrations; the app will create a fresh schema.")
        return

    db_dir = os.path.dirname(resolved_db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with sqlite3.connect(resolved_db_path) as conn:
        cursor = conn.cursor()

        add_missing_columns(
            cursor,
            "user",
            (
                ("is_active", "is_active BOOLEAN DEFAULT 1"),
                ("created_at", "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("totp_secret", "totp_secret VARCHAR"),
                ("pending_totp_secret", "pending_totp_secret VARCHAR"),
            ),
        )
        add_missing_columns(
            cursor,
            "contract",
            (
                ("notice_period", "notice_period INTEGER DEFAULT 30"),
                ("value", "value FLOAT DEFAULT 0.0"),
                ("annual_value", "annual_value FLOAT"),
                ("is_protected", "is_protected BOOLEAN DEFAULT 0"),
                ("version", "version INTEGER DEFAULT 1"),
                ("parent_id", "parent_id INTEGER"),
            ),
        )
        add_missing_columns(
            cursor,
            "contractlist",
            (
                ("description", "description VARCHAR"),
                ("color", "color VARCHAR DEFAULT '#6366f1'"),
                ("created_at", "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ),
        )
        ensure_unique_permission_index(cursor)
        conn.commit()

    print("Migrations completed successfully.")


if __name__ == "__main__":
    migrate()
