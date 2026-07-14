import os
import re
import sqlite3
from collections.abc import Callable, Iterable


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


def table_info(cursor: sqlite3.Cursor, table_name: str) -> list[tuple]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


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


def ensure_migration_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration (
            version VARCHAR PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def migration_applied(cursor: sqlite3.Cursor, version: str) -> bool:
    cursor.execute("SELECT 1 FROM schema_migration WHERE version = ?", (version,))
    return cursor.fetchone() is not None


def record_migration(cursor: sqlite3.Cursor, version: str) -> None:
    cursor.execute("INSERT INTO schema_migration (version) VALUES (?)", (version,))


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


def migration_001_legacy_columns(cursor: sqlite3.Cursor) -> None:
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


def migration_002_document_type(cursor: sqlite3.Cursor) -> None:
    """Mark existing records as contracts and allow invoices to be stored separately."""
    add_missing_columns(
        cursor,
        "contract",
        (("document_type", "document_type VARCHAR NOT NULL DEFAULT 'contract'"),),
    )


def migration_003_contract_end_date_nullable(cursor: sqlite3.Cursor) -> None:
    """Allow invoices and open-ended contracts without losing existing contract rows.

    SQLite cannot remove a ``NOT NULL`` constraint with ``ALTER TABLE``.  For
    legacy databases we therefore recreate the table from its own schema,
    changing only the ``end_date`` column and copying every column and index.
    """
    if not table_exists(cursor, "contract"):
        return

    columns = table_info(cursor, "contract")
    end_date = next((column for column in columns if column[1] == "end_date"), None)

    if end_date is None:
        print("Adding nullable column 'contract.end_date'...")
        cursor.execute("ALTER TABLE contract ADD COLUMN end_date DATETIME")
        return

    # PRAGMA table_info: (cid, name, type, notnull, default_value, pk)
    if not end_date[3]:
        print("Column 'contract.end_date' is already nullable.")
        return

    row = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'contract'"
    ).fetchone()
    if row is None or row[0] is None:
        raise RuntimeError("Could not read the existing contract table schema.")

    original_schema = row[0]
    nullable_schema, constraint_replacements = re.subn(
        r"(\bend_date\b\s+[^,)]*?)\s+NOT\s+NULL\b",
        r"\1",
        original_schema,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if constraint_replacements != 1:
        raise RuntimeError("Could not make the legacy contract.end_date column nullable.")

    rebuilt_schema, table_replacements = re.subn(
        r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"contract\"|`contract`|\[contract\]|contract)\b",
        "CREATE TABLE contract_rebuild",
        nullable_schema,
        count=1,
        flags=re.IGNORECASE,
    )
    if table_replacements != 1:
        raise RuntimeError("Could not prepare a replacement contract table.")

    cursor.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE tbl_name = 'contract' AND type IN ('index', 'trigger') AND sql IS NOT NULL
        """
    )
    schema_objects = [item[0] for item in cursor.fetchall()]
    column_names = [column[1] for column in columns]
    quoted_columns = ", ".join(quote_identifier(column) for column in column_names)

    print("Rebuilding contract table so end_date can be empty...")
    cursor.execute(rebuilt_schema)
    cursor.execute(
        f"INSERT INTO contract_rebuild ({quoted_columns}) "
        f"SELECT {quoted_columns} FROM contract"
    )
    cursor.execute("DROP TABLE contract")
    cursor.execute("ALTER TABLE contract_rebuild RENAME TO contract")
    for statement in schema_objects:
        cursor.execute(statement)


MIGRATIONS: tuple[tuple[str, Callable[[sqlite3.Cursor], None]], ...] = (
    ("001_legacy_columns_and_permission_index", migration_001_legacy_columns),
    ("002_contract_document_type", migration_002_document_type),
    ("003_contract_end_date_nullable", migration_003_contract_end_date_nullable),
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
        ensure_migration_table(cursor)

        for version, migration in MIGRATIONS:
            if migration_applied(cursor, version):
                print(f"Migration '{version}' already applied.")
                continue
            print(f"Applying migration '{version}'...")
            migration(cursor)
            record_migration(cursor, version)
        conn.commit()

    print("Migrations completed successfully.")


if __name__ == "__main__":
    migrate()
