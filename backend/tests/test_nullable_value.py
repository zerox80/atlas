"""Keep legacy totals, links, triggers and never-reused IDs during the nullable migration."""

import sqlite3

from nullable_value_migration import migration_015_nullable_gross_value


def test_nullable_migration_preserves_rows_links_indexes_triggers_and_sequence():
    with sqlite3.connect(":memory:") as db:
        db.executescript("""
            CREATE TABLE contract (id INTEGER PRIMARY KEY AUTOINCREMENT, value FLOAT NOT NULL, title TEXT);
            CREATE TABLE attachment (id INTEGER PRIMARY KEY, contract_id INTEGER REFERENCES contract(id));
            CREATE INDEX value_index ON contract(value);
            CREATE TABLE updates (id INTEGER);
            CREATE TRIGGER contract_update AFTER UPDATE ON contract BEGIN INSERT INTO updates VALUES(new.id); END;
            INSERT INTO contract VALUES(1, 9752.05, 'Original');
            INSERT INTO contract VALUES(100, 119, 'Deleted');
            DELETE FROM contract WHERE id=100;
            INSERT INTO attachment VALUES(1, 1);
        """)
        migration_015_nullable_gross_value(db.cursor())
        migration_015_nullable_gross_value(db.cursor())
        assert db.execute("SELECT * FROM contract").fetchall() == [(1, 9752.05, "Original")]
        new = db.execute("INSERT INTO contract(value, title) VALUES(NULL, 'Unknown')").lastrowid
        assert new > 100
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT * FROM attachment").fetchall() == [(1, 1)]
        assert "value_index" in {row[1] for row in db.execute("PRAGMA index_list(contract)")}
        db.execute("UPDATE contract SET title='Kept' WHERE id=1")
        assert db.execute("SELECT * FROM updates").fetchall() == [(1,)]
