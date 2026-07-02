"""
Tests for SQLite migrations.
"""
import sqlite3

from migrate_db import migrate


def test_migrate_adds_missing_columns_and_deduplicates_permissions(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                username VARCHAR,
                hashed_password VARCHAR,
                role VARCHAR
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE contract (
                id INTEGER PRIMARY KEY,
                title VARCHAR,
                file_path VARCHAR,
                uploaded_at DATETIME
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE contractpermission (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                contract_id INTEGER,
                permission_level VARCHAR
            )
            """
        )
        conn.execute(
            """
            INSERT INTO contractpermission (id, user_id, contract_id, permission_level)
            VALUES (1, 1, 1, 'read'), (2, 1, 1, 'write')
            """
        )
        conn.commit()

    migrate(str(db_path))

    with sqlite3.connect(db_path) as conn:
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(user)")}
        contract_columns = {row[1] for row in conn.execute("PRAGMA table_info(contract)")}
        permission_count = conn.execute("SELECT COUNT(*) FROM contractpermission").fetchone()[0]
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(contractpermission)")}

    assert {"is_active", "created_at", "totp_secret", "pending_totp_secret"} <= user_columns
    assert {"annual_value", "is_protected", "notice_period", "version", "parent_id"} <= contract_columns
    assert permission_count == 1
    assert "ix_contractpermission_user_contract" in indexes
