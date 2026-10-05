"""Allow unknown contract details while preserving legacy SQLite data and schema."""

import re
import sqlite3


def migration_015_nullable_gross_value(cursor: sqlite3.Cursor) -> None:
    _make_contract_columns_nullable(cursor, ("value",))


def migration_016_optional_contract_fields(cursor: sqlite3.Cursor) -> None:
    _make_contract_columns_nullable(
        cursor, ("start_date", "end_date", "notice_period", "value", "annual_value")
    )


def _make_contract_columns_nullable(
    cursor: sqlite3.Cursor, optional_fields: tuple[str, ...]
) -> None:
    from migrate_db import quote_identifier, table_exists, table_info

    if not table_exists(cursor, "contract"):
        return
    columns = table_info(cursor, "contract")
    required_fields = [
        column[1] for column in columns if column[1] in optional_fields and column[3]
    ]
    if not required_fields:
        return
    cursor.execute("SAVEPOINT nullable_contract_fields")
    try:
        schema = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='contract'"
        ).fetchone()[0]
        for field in required_fields:
            name = re.escape(field)
            schema, count = re.subn(
                rf'([(,]\s*(?:"{name}"|`{name}`|\[{name}\]|{name})\s+'
                rf"\w+(?:\s*\([^)]*\))?\s*)NOT\s+NULL\b",
                r"\1",
                schema,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if count != 1:
                raise RuntimeError(f"Could not make contract.{field} nullable")
        schema, count = re.subn(
            r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r'(?:"contract"|`contract`|\[contract\]|contract)(?=\s|\()',
            "CREATE TABLE contract_rebuild",
            schema,
            count=1,
            flags=re.IGNORECASE,
        )
        if count != 1:
            raise RuntimeError("Could not rebuild contract table")
        objects = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='contract' "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
        ).fetchall()
        sequence = (
            cursor.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='contract'"
            ).fetchone()
            if table_exists(cursor, "sqlite_sequence")
            else None
        )
        names = ", ".join(quote_identifier(column[1]) for column in columns)
        cursor.execute(schema)
        cursor.execute(
            f"INSERT INTO contract_rebuild ({names}) SELECT {names} FROM contract"
        )
        cursor.execute("DROP TABLE contract")
        cursor.execute("ALTER TABLE contract_rebuild RENAME TO contract")
        for (statement,) in objects:
            cursor.execute(statement)
        if sequence:
            cursor.execute(
                "UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='contract'",
                sequence,
            )
    except Exception:
        cursor.execute("ROLLBACK TO nullable_contract_fields")
        cursor.execute("RELEASE nullable_contract_fields")
        raise
    cursor.execute("RELEASE nullable_contract_fields")
