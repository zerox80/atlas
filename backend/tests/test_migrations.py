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
        applied_migrations = {
            row[0] for row in conn.execute("SELECT version FROM schema_migration")
        }

    assert {"is_active", "created_at", "totp_secret", "pending_totp_secret"} <= user_columns
    assert {
        "annual_value",
        "is_protected",
        "notice_period",
        "version",
        "parent_id",
        "document_type",
        "end_date",
    } <= contract_columns
    assert permission_count == 1
    assert "ix_contractpermission_user_contract" in indexes
    assert "001_legacy_columns_and_permission_index" in applied_migrations
    assert "002_contract_document_type" in applied_migrations
    assert "003_contract_end_date_nullable" in applied_migrations

    migrate(str(db_path))

    with sqlite3.connect(db_path) as conn:
        migration_count = conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0]

    assert migration_count == 3


def test_migrate_makes_legacy_end_date_nullable_without_losing_contracts(tmp_path):
    db_path = tmp_path / "required_end_date.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE contract (
                id INTEGER PRIMARY KEY,
                title VARCHAR NOT NULL,
                description VARCHAR,
                start_date DATETIME,
                end_date DATETIME NOT NULL,
                file_path VARCHAR NOT NULL,
                document_type VARCHAR NOT NULL DEFAULT 'contract',
                uploaded_at DATETIME NOT NULL,
                notice_period INTEGER DEFAULT 30,
                value FLOAT DEFAULT 0,
                annual_value FLOAT,
                is_protected BOOLEAN DEFAULT 0,
                version INTEGER DEFAULT 1,
                parent_id INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO contract (id, title, end_date, file_path, uploaded_at)
            VALUES (1, 'Bestehender Vertrag', '2027-01-01', 'uploads/old.pdf', '2026-01-01')
            """
        )
        conn.commit()

    migrate(str(db_path))

    with sqlite3.connect(db_path) as conn:
        end_date_info = next(
            row for row in conn.execute("PRAGMA table_info(contract)") if row[1] == "end_date"
        )
        existing_contract = conn.execute(
            "SELECT title, end_date FROM contract WHERE id = 1"
        ).fetchone()
        conn.execute(
            """
            INSERT INTO contract (title, file_path, document_type, uploaded_at, value, is_protected, version)
            VALUES ('Rechnung ohne Laufzeit', 'uploads/invoice.pdf', 'invoice', '2026-07-09', 15.87, 0, 1)
            """
        )
        invoice_count = conn.execute(
            "SELECT COUNT(*) FROM contract WHERE document_type = 'invoice' AND end_date IS NULL"
        ).fetchone()[0]

    assert end_date_info[3] == 0
    assert existing_contract == ("Bestehender Vertrag", "2027-01-01")
    assert invoice_count == 1
