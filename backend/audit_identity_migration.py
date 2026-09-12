"""Keep retained audit records separate from future SQLite document identities."""

import re
import sqlite3


def migration_014_non_reusable_contract_ids(cursor: sqlite3.Cursor) -> None:
    # SQLite DDL does not start a transaction under sqlite3's legacy mode.
    # Keep schema replacement atomic even when all earlier migrations ran before.
    cursor.execute("SAVEPOINT contract_identity_migration")
    try:
        _migrate_contract_identity(cursor)
    except Exception:
        cursor.execute("ROLLBACK TO contract_identity_migration")
        cursor.execute("RELEASE contract_identity_migration")
        raise
    cursor.execute("RELEASE contract_identity_migration")


def _migrate_contract_identity(cursor: sqlite3.Cursor) -> None:
    # Import here because the migration registry imports this module.
    from migrate_db import existing_columns, quote_identifier, table_exists

    if not table_exists(cursor, "contract"):
        return
    schema = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'contract'"
    ).fetchone()[0]
    floor = cursor.execute("SELECT COALESCE(MAX(id), 0) FROM contract").fetchone()[0]
    has_audit = table_exists(cursor, "auditlog")
    if has_audit:
        if "document_history_visible" not in existing_columns(cursor, "auditlog"):
            cursor.execute(
                "ALTER TABLE auditlog ADD COLUMN "
                "document_history_visible BOOLEAN NOT NULL DEFAULT 1"
            )
        floor = max(
            floor,
            cursor.execute(
                "SELECT COALESCE(MAX(contract_id), 0) FROM auditlog"
            ).fetchone()[0],
        )

    if not re.search(r"\bAUTOINCREMENT\b", schema, re.IGNORECASE):
        # Preserve the original column constraints, foreign keys, indexes and
        # triggers. Support both legacy inline and SQLAlchemy table-level PKs;
        # reject unfamiliar schemas instead of silently weakening constraints.
        identifier = r'(?:"id"|`id`|\[id\]|id)'
        column_pattern = rf"([(,]\s*{identifier}\s+INTEGER\b)([^,)]*)"
        column = re.search(column_pattern, schema, re.IGNORECASE)
        if column is None:
            raise RuntimeError("Expected an INTEGER contract.id primary key")
        if re.search(r"\bPRIMARY\s+KEY\b", column[2], re.IGNORECASE):
            replacement = re.sub(
                r"\bPRIMARY\s+KEY\b",
                "PRIMARY KEY AUTOINCREMENT",
                column[0],
                count=1,
                flags=re.IGNORECASE,
            )
            schema = schema[: column.start()] + replacement + schema[column.end() :]
        else:
            schema, count = re.subn(
                rf",\s*PRIMARY\s+KEY\s*\(\s*{identifier}\s*\)",
                "",
                schema,
                count=1,
                flags=re.IGNORECASE,
            )
            if count != 1:
                raise RuntimeError("Expected a single-column contract primary key")
            schema = re.sub(
                column_pattern,
                r"\1\2 PRIMARY KEY AUTOINCREMENT",
                schema,
                count=1,
                flags=re.IGNORECASE,
            )
        schema, count = re.subn(
            r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r'(?:"contract"|`contract`|\[contract\]|contract)(?=\s|\()',
            "CREATE TABLE contract_rebuild",
            schema,
            count=1,
            flags=re.IGNORECASE,
        )
        if count != 1:
            raise RuntimeError("Could not prepare the replacement contract table")
        objects = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'contract' "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
        ).fetchall()
        columns = ", ".join(
            quote_identifier(c) for c in sorted(existing_columns(cursor, "contract"))
        )
        cursor.execute(schema)
        cursor.execute(
            f"INSERT INTO contract_rebuild ({columns}) SELECT {columns} FROM contract"
        )
        cursor.execute("DROP TABLE contract")
        cursor.execute("ALTER TABLE contract_rebuild RENAME TO contract")
        for (statement,) in objects:
            cursor.execute(statement)

    # Include previously deleted IDs, even when no live documents remain.
    row = cursor.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'contract'"
    ).fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('contract', ?)", (floor,)
        )
    else:
        cursor.execute(
            "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'contract'",
            (floor,),
        )

    if has_audit:
        # Old IDs may already have been reused. Their lifetime cannot reliably
        # be inferred from timestamps (including delayed download audit writes).
        # Retain the full records for admins, but quarantine ambiguous links.
        cursor.execute(
            """
            UPDATE auditlog SET document_history_visible = 0
            WHERE contract_id IN (
                SELECT contract_id FROM auditlog
                WHERE action = 'PERMANENTLY_DELETE_DOCUMENT'
            ) OR contract_id NOT IN (SELECT id FROM contract)
            """
        )
