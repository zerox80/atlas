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


def migration_009_workspace_permissions_and_default(cursor: sqlite3.Cursor) -> None:
    """Add workspace ACLs and one isolated Default workspace per user."""
    add_missing_columns(
        cursor,
        "contract",
        (("owner_user_id", "owner_user_id INTEGER"),),
    )

    fallback_owner = None
    if table_exists(cursor, "user"):
        fallback_row = cursor.execute(
            """
            SELECT id FROM "user"
            ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END,
                     CASE WHEN is_active = 1 THEN 0 ELSE 1 END,
                     id
            LIMIT 1
            """
        ).fetchone()
        fallback_owner = int(fallback_row[0]) if fallback_row else None

    if table_exists(cursor, "contract"):
        if table_exists(cursor, "user"):
            cursor.execute(
                """
                UPDATE contract
                SET owner_user_id = NULL
                WHERE owner_user_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM "user" WHERE "user".id = contract.owner_user_id
                  )
                """
            )
        if (
            table_exists(cursor, "user")
            and table_exists(cursor, "auditlog")
            and "contract_id" in existing_columns(cursor, "auditlog")
        ):
            cursor.execute(
                """
                UPDATE contract
                SET owner_user_id = (
                    SELECT auditlog.user_id
                    FROM auditlog
                    WHERE auditlog.contract_id = contract.id
                      AND auditlog.action = 'UPLOAD'
                      AND auditlog.user_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM "user"
                          WHERE "user".id = auditlog.user_id
                      )
                    ORDER BY auditlog.timestamp ASC, auditlog.id ASC
                    LIMIT 1
                )
                WHERE owner_user_id IS NULL
                """
            )
        if table_exists(cursor, "user") and table_exists(
            cursor, "contractpermission"
        ):
            cursor.execute(
                """
                UPDATE contract
                SET owner_user_id = (
                    SELECT contractpermission.user_id
                    FROM contractpermission
                    WHERE contractpermission.contract_id = contract.id
                      AND contractpermission.permission_level = 'full'
                      AND EXISTS (
                          SELECT 1 FROM "user"
                          WHERE "user".id = contractpermission.user_id
                      )
                    ORDER BY contractpermission.id ASC
                    LIMIT 1
                )
                WHERE owner_user_id IS NULL
                """
            )
        if fallback_owner is not None:
            cursor.execute(
                "UPDATE contract SET owner_user_id = ? WHERE owner_user_id IS NULL",
                (fallback_owner,),
            )

    # Very old installations may not have used collections yet. Their contract
    # owners are still migrated above; create_all and the startup backfill will
    # then create the current workspace tables and isolated Defaults.
    if not table_exists(cursor, "contractlist"):
        return

    add_missing_columns(
        cursor,
        "contractlist",
        (
            ("owner_user_id", "owner_user_id INTEGER"),
            ("is_default", "is_default BOOLEAN NOT NULL DEFAULT 0"),
        ),
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS contractlistpermission (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            list_id INTEGER NOT NULL,
            permission_level VARCHAR NOT NULL DEFAULT 'read',
            CONSTRAINT uq_contractlistpermission_user_list
                UNIQUE (user_id, list_id),
            FOREIGN KEY(user_id) REFERENCES "user" (id),
            FOREIGN KEY(list_id) REFERENCES contractlist (id)
        )
        """
    )
    cursor.execute(
        """
        DELETE FROM contractlistpermission
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM contractlistpermission
            GROUP BY user_id, list_id
        )
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        ix_contractlistpermission_user_list
        ON contractlistpermission (user_id, list_id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        ix_contractlistpermission_user_level_list
        ON contractlistpermission (user_id, permission_level, list_id)
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_contractlistpermission_user_id "
        "ON contractlistpermission (user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_contractlistpermission_list_id "
        "ON contractlistpermission (list_id)"
    )

    if table_exists(cursor, "user"):
        cursor.execute(
            """
            UPDATE contractlist
            SET owner_user_id = NULL
            WHERE owner_user_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM "user"
                  WHERE "user".id = contractlist.owner_user_id
              )
            """
        )
    if fallback_owner is not None:
        cursor.execute(
            "UPDATE contractlist SET owner_user_id = ? WHERE owner_user_id IS NULL",
            (fallback_owner,),
        )

    cursor.execute("DROP INDEX IF EXISTS ix_contractlist_single_default")
    cursor.execute(
        """
        UPDATE contractlist
        SET is_default = 0
        WHERE is_default = 1
          AND id NOT IN (
              SELECT MIN(id)
              FROM contractlist
              WHERE is_default = 1
              GROUP BY owner_user_id
          )
        """
    )

    users = (
        cursor.execute('SELECT id FROM "user" ORDER BY id').fetchall()
        if table_exists(cursor, "user")
        else []
    )
    for (user_id_value,) in users:
        user_id = int(user_id_value)
        existing_default = cursor.execute(
            """
            SELECT id FROM contractlist
            WHERE owner_user_id = ? AND is_default = 1
            ORDER BY id LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if existing_default:
            default_list_id = int(existing_default[0])
        else:
            cursor.execute(
                """
                INSERT INTO contractlist
                    (owner_user_id, name, description, color, is_default, created_at)
                VALUES
                    (?, 'Default', 'Persönlicher Standard-Workspace',
                     '#6366f1', 1, CURRENT_TIMESTAMP)
                """,
                (user_id,),
            )
            default_list_id = int(cursor.lastrowid)
        cursor.execute(
            "UPDATE contractlist SET name = 'Default' WHERE id = ?",
            (default_list_id,),
        )
        cursor.execute(
            """
            INSERT INTO contractlistpermission
                (user_id, list_id, permission_level)
            VALUES (?, ?, 'full')
            ON CONFLICT(user_id, list_id)
            DO UPDATE SET permission_level = excluded.permission_level
            """,
            (user_id, default_list_id),
        )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        ix_contractlist_owner_single_default
        ON contractlist (owner_user_id)
        WHERE is_default = 1 AND owner_user_id IS NOT NULL
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_contractlist_is_default "
        "ON contractlist (is_default)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_contractlist_owner_user_id "
        "ON contractlist (owner_user_id)"
    )
    if table_exists(cursor, "contract"):
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_contract_owner_user_id "
            "ON contract (owner_user_id)"
        )

    if table_exists(cursor, "contract") and table_exists(cursor, "contractlistlink"):
        # A Default is private to its owner. Repair any legacy/global Default links.
        cursor.execute(
            """
            DELETE FROM contractlistlink
            WHERE EXISTS (
                SELECT 1
                FROM contractlist
                JOIN contract ON contract.id = contractlistlink.contract_id
                WHERE contractlist.id = contractlistlink.list_id
                  AND contractlist.is_default = 1
                  AND contract.owner_user_id IS NOT contractlist.owner_user_id
            )
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO contractlistlink (contract_id, list_id)
            SELECT contract.id, contractlist.id
            FROM contract
            JOIN contractlist
              ON contractlist.owner_user_id = contract.owner_user_id
             AND contractlist.is_default = 1
            WHERE NOT EXISTS (
                SELECT 1
                FROM contractlistlink
                WHERE contractlistlink.contract_id = contract.id
            )
            """
        )


def migration_010_admin_selected_default_workspace(cursor: sqlite3.Cursor) -> None:
    """Persist an explicit, permission-independent upload target per user."""
    if not table_exists(cursor, "user"):
        return

    add_missing_columns(
        cursor,
        "user",
        (("default_workspace_id", "default_workspace_id INTEGER"),),
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_default_workspace_id "
        "ON \"user\" (default_workspace_id)"
    )
    if not table_exists(cursor, "contractlist"):
        return
    # Existing users start on their own isolated personal workspace. A shared
    # permission is deliberately never inferred as the default upload target.
    cursor.execute(
        """
        UPDATE "user"
        SET default_workspace_id = (
            SELECT contractlist.id
            FROM contractlist
            WHERE contractlist.owner_user_id = "user".id
              AND contractlist.is_default = 1
            ORDER BY contractlist.id
            LIMIT 1
        )
        """
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
    (
        "009_workspace_permissions_and_default_collection",
        migration_009_workspace_permissions_and_default,
    ),
    (
        "010_admin_selected_default_workspace",
        migration_010_admin_selected_default_workspace,
    ),
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
