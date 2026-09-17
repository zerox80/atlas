"""Unknown gross totals stay unknown when creating entries from a mixed PDF."""

import re
import sqlite3


def migration_015_nullable_gross_value(cursor: sqlite3.Cursor) -> None:
    from migrate_db import quote_identifier, table_exists, table_info

    if not table_exists(cursor, "contract"):
        return
    columns = table_info(cursor, "contract")
    value = next((column for column in columns if column[1] == "value"), None)
    if value is None or not value[3]:
        return
    cursor.execute("SAVEPOINT nullable_gross_value")
    try:
        schema = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='contract'").fetchone()[0]
        schema, count = re.subn(r'((?:"value"|`value`|\[value\]|\bvalue\b)\s+[^,)]*?)\s+NOT\s+NULL\b',
                                r"\1", schema, count=1, flags=re.I | re.S)
        if count != 1:
            raise RuntimeError("Could not make contract.value nullable")
        schema, count = re.subn(r'^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
                                r'(?:"contract"|`contract`|\[contract\]|contract)(?=\s|\()',
                                "CREATE TABLE contract_rebuild", schema, count=1, flags=re.I)
        if count != 1:
            raise RuntimeError("Could not rebuild contract table")
        objects = cursor.execute("SELECT sql FROM sqlite_master WHERE tbl_name='contract' "
                                 "AND type IN ('index', 'trigger') AND sql IS NOT NULL").fetchall()
        sequence = (cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='contract'").fetchone()
                    if table_exists(cursor, "sqlite_sequence") else None)
        names = ", ".join(quote_identifier(column[1]) for column in columns)
        cursor.execute(schema)
        cursor.execute(f"INSERT INTO contract_rebuild ({names}) SELECT {names} FROM contract")
        cursor.execute("DROP TABLE contract")
        cursor.execute("ALTER TABLE contract_rebuild RENAME TO contract")
        for (statement,) in objects:
            cursor.execute(statement)
        if sequence:
            cursor.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='contract'", sequence)
    except Exception:
        cursor.execute("ROLLBACK TO nullable_gross_value")
        cursor.execute("RELEASE nullable_gross_value")
        raise
    cursor.execute("RELEASE nullable_gross_value")
