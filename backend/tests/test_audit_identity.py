"""Regression coverage for retained history and reusable document IDs."""

import sqlite3
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from audit_identity_migration import migration_014_non_reusable_contract_ids
from main import app, get_current_user
from models import AuditLog, Contract, ContractPermission


@pytest.mark.parametrize("document_type", ["contract", "invoice"])
def test_deleted_document_history_does_not_follow_new_owner(
    client,
    session,
    test_user,
    admin_user,
    document_type,
):
    victim = Contract(
        title="Victim secret",
        file_path="uploads/missing.pdf",
        owner_user_id=admin_user.id,
        document_type=document_type,
        deleted_at=datetime.now(timezone.utc),
    )
    session.add(victim)
    session.flush()
    old_id = victim.id
    session.add(
        AuditLog(
            user_id=admin_user.id,
            contract_id=old_id,
            action="UPLOAD",
            details="Victim confidential values",
        )
    )
    session.commit()
    app.dependency_overrides[get_current_user] = lambda: admin_user
    response = client.delete(f"/trash/{old_id}/permanent?version=1")
    assert response.status_code == 204, response.text
    # The same database allocation boundary used by the upload route.
    replacement = Contract(
        title="New document",
        file_path="uploads/new.pdf",
        owner_user_id=test_user.id,
        document_type=document_type,
    )
    session.add(replacement)
    session.flush()
    session.add(
        ContractPermission(
            user_id=test_user.id, contract_id=replacement.id, permission_level="full"
        )
    )
    session.add(
        AuditLog(
            user_id=test_user.id,
            contract_id=replacement.id,
            action="UPLOAD",
            details="New owner history",
        )
    )
    session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    response = client.get(f"/contracts/{replacement.id}/audit")
    assert response.status_code == 200
    assert [item["details"] for item in response.json()["items"]] == [
        "New owner history"
    ]
    assert replacement.id > old_id
    assert client.get(f"/contracts/{old_id}/audit").status_code == 404
    assert client.get("/audit-logs").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: admin_user
    assert "Victim confidential values" in {
        item["details"] for item in client.get("/audit-logs").json()
    }


def test_ambiguous_legacy_history_is_admin_only(client, session, test_user, admin_user):
    contract = Contract(title="Current document", file_path="uploads/new.pdf")
    session.add(contract)
    session.flush()
    session.add(
        ContractPermission(
            user_id=test_user.id, contract_id=contract.id, permission_level="read"
        )
    )
    session.add(
        AuditLog(
            user_id=admin_user.id,
            contract_id=contract.id,
            action="DOWNLOAD",
            details="Ambiguous old title",
            document_history_visible=False,
        )
    )
    session.add(
        AuditLog(
            user_id=test_user.id,
            contract_id=contract.id,
            action="UPLOAD",
            details="Current history",
        )
    )
    session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    response = client.get(f"/contracts/{contract.id}/audit?limit=1")
    assert response.status_code == 200
    assert [item["details"] for item in response.json()["items"]] == ["Current history"]
    assert response.json()["has_more"] is False
    app.dependency_overrides[get_current_user] = lambda: admin_user
    assert "Ambiguous old title" in {
        item["details"] for item in client.get("/audit-logs").json()
    }
    assert (
        session.exec(select(AuditLog).where(AuditLog.details == "Ambiguous old title"))
        .one()
        .contract_id
        == contract.id
    )


@pytest.mark.parametrize(
    "pk",
    [
        "id INTEGER PRIMARY KEY",
        "id INTEGER NOT NULL, PRIMARY KEY (id)",
        '"id" INTEGER NOT NULL, PRIMARY KEY ("id")',
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_legacy_migration_preserves_schema_and_reserves_retained_ids(
    tmp_path, pk, empty
):
    with sqlite3.connect(tmp_path / "legacy.db") as conn:
        first, *constraint = pk.split(", ")
        suffix = ", " + constraint[0] if constraint else ""
        conn.execute(
            f'CREATE TABLE "contract" ({first}, title TEXT NOT NULL, '
            f"parent_id INTEGER REFERENCES contract(id), extra TEXT DEFAULT 'kept'{suffix})"
        )
        conn.execute("CREATE INDEX custom_title ON contract(title)")
        conn.execute("CREATE TABLE touched (id INTEGER)")
        conn.execute(
            "CREATE TRIGGER custom_insert AFTER INSERT ON contract "
            "BEGIN INSERT INTO touched VALUES (new.id); END"
        )
        conn.execute("CREATE TABLE child (contract_id INTEGER REFERENCES contract(id))")
        conn.execute(
            "CREATE TABLE auditlog (id INTEGER PRIMARY KEY, contract_id INTEGER, "
            "action TEXT, details TEXT)"
        )
        if not empty:
            conn.execute("INSERT INTO contract (id, title) VALUES (1, 'retained')")
            conn.execute(
                "INSERT INTO contract (id, title, parent_id) VALUES (2, 'child', 1)"
            )
            conn.execute("INSERT INTO child VALUES (1)")
        conn.executemany(
            "INSERT INTO auditlog VALUES (?, ?, ?, ?)",
            [
                (1, 1, "UPLOAD", "ambiguous prior lifetime"),
                (2, 1, "PERMANENTLY_DELETE_DOCUMENT", "deleted"),
                (3, 1, "DOWNLOAD", "late old download"),
                (4, 2, "UPLOAD", "legitimate child"),
                (5, 99, "UPLOAD", "orphan secret"),
            ],
        )
        if "AUTOINCREMENT" in pk:
            conn.execute("INSERT INTO contract (id, title) VALUES (150, 'gone')")
            conn.execute("DELETE FROM contract WHERE id = 150")
        migration_014_non_reusable_contract_ids(conn.cursor())
        before = conn.execute(
            "SELECT id, contract_id, action, details FROM auditlog"
        ).fetchall()
        assert len(before) == 5
        visible = dict(
            conn.execute("SELECT id, document_history_visible FROM auditlog")
        )
        assert visible == {1: 0, 2: 0, 3: 0, 4: int(not empty), 5: 0}
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        new_id = conn.execute("INSERT INTO contract (title) VALUES ('new')").lastrowid
        assert new_id > (150 if "AUTOINCREMENT" in pk else 99)
        assert conn.execute(
            "SELECT extra FROM contract WHERE id = ?", (new_id,)
        ).fetchone() == ("kept",)
        assert conn.execute(
            "SELECT id FROM touched ORDER BY rowid DESC LIMIT 1"
        ).fetchone() == (new_id,)
        assert "custom_title" in {
            r[1] for r in conn.execute("PRAGMA index_list(contract)")
        }
        if not empty:
            assert conn.execute(
                "SELECT parent_id FROM contract WHERE id = 2"
            ).fetchone() == (1,)
        conn.execute("DELETE FROM contract WHERE id = ?", (new_id,))
        migration_014_non_reusable_contract_ids(conn.cursor())
        next_id = conn.execute("INSERT INTO contract (title) VALUES ('next')").lastrowid
        assert next_id > new_id
        assert (
            conn.execute(
                "SELECT id, contract_id, action, details FROM auditlog"
            ).fetchall()
            == before
        )


def test_failed_migration_rolls_back_schema_changes(tmp_path):
    with sqlite3.connect(tmp_path / "unsupported.db") as conn:
        conn.execute("CREATE TABLE contract (id TEXT PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE auditlog (id INTEGER PRIMARY KEY, contract_id INTEGER, action TEXT)"
        )
        conn.commit()
        with pytest.raises(RuntimeError, match="INTEGER"):
            migration_014_non_reusable_contract_ids(conn.cursor())
        assert "document_history_visible" not in {
            row[1] for row in conn.execute("PRAGMA table_info(auditlog)")
        }
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE name = 'contract_rebuild'"
            ).fetchall()
            == []
        )
