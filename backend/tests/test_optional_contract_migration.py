"""Upgrade real legacy constraints, not just freshly generated model tables."""

import sqlite3

import pytest

from migrate_db import MIGRATIONS, migrate
from nullable_value_migration import migration_016_optional_contract_fields

OPTIONAL_FIELDS = ("start_date", "end_date", "notice_period", "value", "annual_value")


def create_legacy_schema(db, quote='"'):
    def identifier(name):
        return f"{quote}{name}{']' if quote == '[' else quote}"

    db.executescript(f"""
        CREATE TABLE {identifier("contract")} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR NOT NULL,
            file_path VARCHAR NOT NULL,
            uploaded_at DATETIME NOT NULL,
            {identifier("start_date")} DATETIME NOT NULL,
            {identifier("end_date")} DATETIME NOT NULL,
            {identifier("notice_period")} INTEGER NOT NULL DEFAULT 30,
            {identifier("value")} FLOAT NOT NULL DEFAULT 0,
            {identifier("annual_value")} NUMERIC(18, 2) NOT NULL,
            parent_id INTEGER REFERENCES contract(id),
            custom_column TEXT DEFAULT 'notice_period INTEGER NOT NULL'
        );
        CREATE TABLE attachment (
            id INTEGER PRIMARY KEY,
            contract_id INTEGER REFERENCES contract(id) ON DELETE CASCADE
        );
        CREATE INDEX notice_index ON contract(notice_period);
        CREATE TABLE updates (id INTEGER);
        CREATE TRIGGER contract_update AFTER UPDATE ON contract
            BEGIN INSERT INTO updates VALUES(new.id); END;
        INSERT INTO contract (id, title, file_path, uploaded_at, start_date,
                              end_date, notice_period, value, annual_value)
        VALUES (1, 'Original', 'uploads/original.pdf', '2026-01-01',
                '2026-01-01', '2027-01-01', 30, 9752.05, 123.45);
        INSERT INTO contract (id, title, file_path, uploaded_at, start_date,
                              end_date, notice_period, value, annual_value, parent_id)
        VALUES (2, 'Child', 'uploads/child.pdf', '2026-01-01',
                '2026-01-01', '2027-01-01', 0, 0, 0, 1);
        INSERT INTO contract (id, title, file_path, uploaded_at, start_date,
                              end_date, notice_period, value, annual_value)
        VALUES (100, 'Deleted', 'uploads/deleted.pdf', '2026-01-01',
                '2026-01-01', '2027-01-01', 30, 10, 10);
        DELETE FROM contract WHERE id=100;
        INSERT INTO attachment VALUES(1, 1);
    """)


def insert_unknown(db):
    return db.execute("""
        INSERT INTO contract (title, file_path, uploaded_at,
                              start_date, end_date, notice_period, value, annual_value)
        VALUES ('Unknown', 'uploads/new.pdf', '2026-10-05', NULL, NULL, NULL, NULL, NULL)
    """).lastrowid


def assert_optional_columns(db):
    columns = {row[1]: row for row in db.execute("PRAGMA table_info(contract)")}
    assert all(columns[field][3] == 0 for field in OPTIONAL_FIELDS)
    assert columns["title"][3] == columns["file_path"][3] == 1


@pytest.mark.parametrize("quote", ["", '"', "`", "["])
def test_optional_migration_preserves_data_links_schema_and_sequence(quote):
    with sqlite3.connect(":memory:") as db:
        create_legacy_schema(db, quote)
        original_rows = db.execute("SELECT * FROM contract ORDER BY id").fetchall()
        migration_016_optional_contract_fields(db.cursor())
        schema = db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
        migration_016_optional_contract_fields(db.cursor())
        assert (
            db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
            == schema
        )
        assert (
            db.execute("SELECT * FROM contract ORDER BY id").fetchall() == original_rows
        )
        assert_optional_columns(db)
        db.commit()
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT * FROM attachment").fetchall() == [(1, 1)]
        assert (
            db.execute("PRAGMA foreign_key_list(contract)").fetchone()[2] == "contract"
        )
        assert "notice_index" in {
            row[1] for row in db.execute("PRAGMA index_list(contract)")
        }
        assert insert_unknown(db) > 100
        db.execute("UPDATE contract SET title='Kept' WHERE id=1")
        assert db.execute("SELECT * FROM updates").fetchall() == [(1,)]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE contract SET parent_id=999 WHERE id=2")


def test_optional_migration_keeps_sequence_for_empty_table():
    with sqlite3.connect(":memory:") as db:
        create_legacy_schema(db)
        db.execute("DELETE FROM attachment")
        db.execute("DELETE FROM contract")
        migration_016_optional_contract_fields(db.cursor())
        assert insert_unknown(db) > 100


@pytest.mark.parametrize("applied_count", [0, 7, 15])
def test_upgrade_existing_database_and_rerun(tmp_path, applied_count):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as db:
        create_legacy_schema(db)
        if applied_count:
            # Simulate the affected installation: 015 is recorded but the
            # optional columns still have legacy NOT NULL constraints.
            db.execute("CREATE TABLE schema_migration (version VARCHAR PRIMARY KEY)")
            db.executemany(
                "INSERT INTO schema_migration VALUES (?)",
                [(version,) for version, _ in MIGRATIONS[:applied_count]],
            )
        if applied_count < 8:
            # Migration 008 must be able to replace invalid values with NULL
            # before reaching the new migration at the end of the registry.
            db.execute(
                "UPDATE contract SET notice_period=-1, annual_value=-1 WHERE id=1"
            )

    migrate(str(db_path))
    migrate(str(db_path))
    with sqlite3.connect(db_path) as db:
        assert_optional_columns(db)
        assert db.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == len(
            MIGRATIONS
        )
        assert db.execute("SELECT COUNT(*) FROM contract").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT * FROM attachment").fetchall() == [(1, 1)]
        assert insert_unknown(db) > 100
        if applied_count < 8:
            assert db.execute(
                "SELECT notice_period, annual_value FROM contract WHERE id=1"
            ).fetchone() == (None, None)


def test_failed_rebuild_rolls_back_schema_data_and_sequence():
    with sqlite3.connect(":memory:") as db:
        create_legacy_schema(db)
        original_schema = db.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
        original_rows = db.execute("SELECT * FROM contract ORDER BY id").fetchall()

        def reject_index_creation(action, name, *_):
            if action == sqlite3.SQLITE_CREATE_INDEX and name == "notice_index":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(reject_index_creation)
        with pytest.raises(sqlite3.DatabaseError):
            migration_016_optional_contract_fields(db.cursor())
        db.set_authorizer(None)
        assert (
            db.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
            == original_schema
        )
        assert (
            db.execute("SELECT * FROM contract ORDER BY id").fetchall() == original_rows
        )
        assert db.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='contract'"
        ).fetchone() == (100,)
        # A failed attempt can be retried without a stale rebuild table.
        migration_016_optional_contract_fields(db.cursor())
        assert insert_unknown(db) > 100
