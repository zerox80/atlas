"""
Regression tests for contract access control and related data cleanup.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from main import app, get_current_user
from main import backfill_existing_contract_read_permissions
from models import (
    AuditLog,
    Contract,
    ContractList,
    ContractListLink,
    ContractPermission,
    ContractTagLink,
    Tag,
    User,
)


def authenticate_as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def create_contract(session: Session, title: str) -> Contract:
    contract = Contract(title=title, file_path=f"uploads/{title.lower().replace(' ', '-')}.pdf")
    session.add(contract)
    session.commit()
    session.refresh(contract)
    return contract


def grant_permission(session: Session, user: User, contract: Contract, level: str = "read") -> ContractPermission:
    permission = ContractPermission(
        user_id=user.id,
        contract_id=contract.id,
        permission_level=level,
    )
    session.add(permission)
    session.commit()
    session.refresh(permission)
    return permission


class TestContractPermissions:
    def test_contract_list_requires_explicit_read_permission(
        self,
        client: TestClient,
        session: Session,
        test_user: User,
        admin_user: User,
    ):
        visible = create_contract(session, "Visible Contract")
        create_contract(session, "Hidden Contract")
        grant_permission(session, test_user, visible, "read")

        authenticate_as(test_user)
        response = client.get("/contracts")
        assert response.status_code == 200
        assert [contract["title"] for contract in response.json()] == ["Visible Contract"]
        visible_payload = response.json()[0]
        assert visible_payload["can_read"] is True
        assert visible_payload["can_write"] is False
        assert visible_payload["can_delete"] is False
        assert visible_payload["can_manage_protection"] is False

        authenticate_as(admin_user)
        response = client.get("/contracts")
        assert response.status_code == 200
        titles = {contract["title"] for contract in response.json()}
        assert titles == {"Visible Contract", "Hidden Contract"}
        assert all(contract["can_write"] is True for contract in response.json())
        assert all(contract["can_delete"] is True for contract in response.json())

    def test_acl_backfill_grants_read_once_for_existing_contracts(
        self,
        session: Session,
        test_user: User,
    ):
        existing_contract = create_contract(session, "Existing Contract")
        full_access_contract = create_contract(session, "Full Access Contract")
        grant_permission(session, test_user, full_access_contract, "full")

        created = backfill_existing_contract_read_permissions(session)
        assert created == 1

        read_permission = session.exec(
            select(ContractPermission)
            .where(ContractPermission.user_id == test_user.id)
            .where(ContractPermission.contract_id == existing_contract.id)
        ).first()
        full_permission = session.exec(
            select(ContractPermission)
            .where(ContractPermission.user_id == test_user.id)
            .where(ContractPermission.contract_id == full_access_contract.id)
        ).first()
        assert read_permission is not None
        assert full_permission is not None
        assert read_permission.permission_level == "read"
        assert full_permission.permission_level == "full"

        assert backfill_existing_contract_read_permissions(session) == 0
        permissions = session.exec(select(ContractPermission)).all()
        assert len(permissions) == 2

    def test_export_only_contains_readable_contracts(
        self,
        client: TestClient,
        session: Session,
        test_user: User,
    ):
        visible = create_contract(session, "Export Visible")
        create_contract(session, "Export Hidden")
        grant_permission(session, test_user, visible, "read")

        authenticate_as(test_user)
        response = client.get("/contracts/export")
        assert response.status_code == 200

        csv_body = response.content.decode("utf-8-sig")
        assert "Export Visible" in csv_body
        assert "Export Hidden" not in csv_body

    def test_contract_audit_requires_read_permission(
        self,
        client: TestClient,
        session: Session,
        test_user: User,
    ):
        contract = create_contract(session, "Audited Contract")
        session.add(AuditLog(
            user_id=test_user.id,
            action="UPDATE_CONTRACT",
            details=f"[CID:{contract.id}] Changed confidential details",
        ))
        session.commit()

        authenticate_as(test_user)
        response = client.get(f"/contracts/{contract.id}/audit")
        assert response.status_code == 403

        grant_permission(session, test_user, contract, "read")
        response = client.get(f"/contracts/{contract.id}/audit")
        assert response.status_code == 200
        assert response.json()["items"][0]["action"] == "UPDATE_CONTRACT"


class TestListPermissions:
    def test_regular_users_cannot_manage_global_lists(
        self,
        client: TestClient,
        session: Session,
        test_user: User,
    ):
        lst = ContractList(name="Admin Managed")
        contract = create_contract(session, "List Contract")
        session.add(lst)
        session.commit()
        session.refresh(lst)

        authenticate_as(test_user)
        assert client.post("/lists", json={"name": "User List"}).status_code == 403
        assert client.put(f"/lists/{lst.id}", json={"name": "Changed"}).status_code == 403
        assert client.delete(f"/lists/{lst.id}").status_code == 403
        assert client.post(f"/lists/{lst.id}/contracts/{contract.id}").status_code == 403
        assert client.delete(f"/lists/{lst.id}/contracts/{contract.id}").status_code == 403

    def test_list_reads_are_filtered_by_contract_permission(
        self,
        client: TestClient,
        session: Session,
        test_user: User,
    ):
        visible_contract = create_contract(session, "Readable Listed")
        hidden_contract = create_contract(session, "Hidden Listed")
        visible_list = ContractList(name="Visible List")
        hidden_list = ContractList(name="Hidden List")
        session.add(visible_list)
        session.add(hidden_list)
        session.commit()
        session.refresh(visible_list)
        session.refresh(hidden_list)

        session.add(ContractListLink(list_id=visible_list.id, contract_id=visible_contract.id))
        session.add(ContractListLink(list_id=visible_list.id, contract_id=hidden_contract.id))
        session.add(ContractListLink(list_id=hidden_list.id, contract_id=hidden_contract.id))
        grant_permission(session, test_user, visible_contract, "read")
        session.commit()

        authenticate_as(test_user)
        response = client.get("/lists")
        assert response.status_code == 200
        lists = response.json()
        assert len(lists) == 1
        assert lists[0]["id"] == visible_list.id
        assert lists[0]["name"] == "Visible List"
        assert lists[0]["contract_count"] == 1

        response = client.get(f"/lists/{visible_list.id}/contracts")
        assert response.status_code == 200
        assert [contract["title"] for contract in response.json()] == ["Readable Listed"]

        response = client.get(f"/lists/{hidden_list.id}")
        assert response.status_code == 404


class TestContractDeleteCleanup:
    def test_delete_contract_removes_links_and_permissions(
        self,
        admin_client: TestClient,
        session: Session,
        test_user: User,
    ):
        contract = create_contract(session, "Delete Cleanup")
        tag = Tag(name="Cleanup")
        lst = ContractList(name="Cleanup List")
        session.add(tag)
        session.add(lst)
        session.commit()
        session.refresh(tag)
        session.refresh(lst)

        session.add(ContractTagLink(contract_id=contract.id, tag_id=tag.id))
        session.add(ContractListLink(contract_id=contract.id, list_id=lst.id))
        grant_permission(session, test_user, contract, "full")
        session.commit()

        response = admin_client.delete(f"/contracts/{contract.id}")
        assert response.status_code == 204

        assert session.get(Contract, contract.id) is None
        assert session.exec(select(ContractTagLink).where(ContractTagLink.contract_id == contract.id)).all() == []
        assert session.exec(select(ContractListLink).where(ContractListLink.contract_id == contract.id)).all() == []
        assert session.exec(select(ContractPermission).where(ContractPermission.contract_id == contract.id)).all() == []
