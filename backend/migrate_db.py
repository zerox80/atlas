import math
import os
import re
import sqlite3
from collections.abc import Callable, Iterable
from uuid import UUID, uuid4


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


def migration_004_audit_contract_id(cursor: sqlite3.Cursor) -> None:
    """Store contract references structurally so audit history can use an index."""
    add_missing_columns(
        cursor,
        "auditlog",
        (("contract_id", "contract_id INTEGER"),),
    )
    if not table_exists(cursor, "auditlog"):
        return

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_auditlog_contract_id ON auditlog (contract_id)"
    )
    rows = cursor.execute(
        "SELECT id, details FROM auditlog WHERE contract_id IS NULL"
    ).fetchall()
    for audit_id, details in rows:
        match = re.search(r"\[CID:(\d+)\]", details or "")
        if match:
            cursor.execute(
                "UPDATE auditlog SET contract_id = ? WHERE id = ?",
                (int(match.group(1)), audit_id),
            )


def migration_005_contract_query_indexes(cursor: sqlite3.Cursor) -> None:
    """Add indexes for the document list, calendar, and ACL lookup hot paths."""
    if table_exists(cursor, "contract"):
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_contract_document_uploaded_at "
            "ON contract (document_type, uploaded_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_contract_end_date ON contract (end_date)"
        )
    if table_exists(cursor, "contractpermission"):
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_contractpermission_user_level_contract "
            "ON contractpermission (user_id, permission_level, contract_id)"
        )


def migration_006_user_token_version(cursor: sqlite3.Cursor) -> None:
    """Add the server-side session generation used to revoke issued JWTs."""
    add_missing_columns(
        cursor,
        "user",
        (("token_version", "token_version INTEGER NOT NULL DEFAULT 0"),),
    )


def migration_007_user_auth_subject(cursor: sqlite3.Cursor) -> None:
    """Give every user an immutable random identity for JWT subject lookup."""
    if not table_exists(cursor, "user"):
        return

    add_missing_columns(
        cursor,
        "user",
        (("auth_subject", "auth_subject VARCHAR"),),
    )

    rows = cursor.execute(
        'SELECT id, auth_subject FROM "user" ORDER BY id'
    ).fetchall()

    def is_uuid4(subject: object) -> bool:
        if not isinstance(subject, str) or not subject:
            return False
        try:
            parsed_subject = UUID(subject)
        except ValueError:
            return False
        return parsed_subject.version == 4 and str(parsed_subject) == subject.lower()

    reserved_subjects = {
        subject.lower()
        for _, subject in rows
        if isinstance(subject, str) and subject
    }
    assigned_subjects: set[str] = set()
    for user_id, current_subject in rows:
        normalized_subject = (
            current_subject.lower() if isinstance(current_subject, str) else ""
        )
        if is_uuid4(current_subject) and normalized_subject not in assigned_subjects:
            assigned_subjects.add(normalized_subject)
            continue

        auth_subject = str(uuid4())
        while auth_subject in reserved_subjects or auth_subject in assigned_subjects:
            auth_subject = str(uuid4())
        cursor.execute(
            'UPDATE "user" SET auth_subject = ? WHERE id = ?',
            (auth_subject, user_id),
        )
        assigned_subjects.add(auth_subject)

    cursor.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_auth_subject '
        'ON "user" (auth_subject)'
    )


def migration_008_sanitize_contract_numeric_values(cursor: sqlite3.Cursor) -> None:
    """Normalize legacy numeric values that cannot be represented safely in JSON."""
    if not table_exists(cursor, "contract"):
        return

    def normalize_financial(value: object, fallback: float | None) -> float | None:
        if value is None:
            return fallback
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return fallback
        if not math.isfinite(parsed) or parsed < 0:
            return fallback
        return min(parsed, 1_000_000_000_000_000.0)

    rows = cursor.execute(
        "SELECT id, value, annual_value, notice_period FROM contract"
    ).fetchall()
    for (
        contract_id,
        value,
        annual_value,
        notice_period,
    ) in rows:
        clean_value = normalize_financial(value, 0.0)
        clean_annual_value = normalize_financial(annual_value, None)
        if isinstance(notice_period, int) and 0 <= notice_period <= 36_500:
            clean_notice_period = notice_period
        else:
            clean_notice_period = 30
        cursor.execute(
            """
            UPDATE contract
            SET value = ?, annual_value = ?, notice_period = ?
            WHERE id = ?
            """,
            (
                clean_value,
                clean_annual_value,
                clean_notice_period,
                contract_id,
            ),
        )


MIGRATIONS: tuple[tuple[str, Callable[[sqlite3.Cursor], None]], ...] = (
    ("001_legacy_columns_and_permission_index", migration_001_legacy_columns),
    ("002_contract_document_type", migration_002_document_type),
    ("003_contract_end_date_nullable", migration_003_contract_end_date_nullable),
    ("004_audit_contract_id", migration_004_audit_contract_id),
    ("005_contract_query_indexes", migration_005_contract_query_indexes),
    ("006_user_token_version", migration_006_user_token_version),
    ("007_user_auth_subject", migration_007_user_auth_subject),
    ("008_sanitize_contract_numeric_values", migration_008_sanitize_contract_numeric_values),
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
