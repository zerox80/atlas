"""
Tests for contract CRUD endpoints.
"""
from fastapi.testclient import TestClient
from sqlmodel import select

from models import AuditLog, Contract, ContractPermission


class TestContractList:
    """Test contract listing."""
    
    def test_get_contracts_empty(self, auth_client: TestClient):
        """Test getting contracts when none exist."""
        response = auth_client.get("/contracts")
        assert response.status_code == 200
        assert response.json() == []
    
    def test_get_contracts_unauthenticated(self, client: TestClient):
        """Test that unauthenticated users cannot access contracts."""
        response = client.get("/contracts")
        assert response.status_code == 401

    def test_filter_by_document_type(self, auth_client: TestClient, session, test_user):
        contract = Contract(title="Service Agreement", file_path="uploads/service.txt")
        invoice = Contract(
            title="April Invoice",
            file_path="uploads/invoice.txt",
            document_type="invoice",
        )
        session.add(contract)
        session.add(invoice)
        session.commit()
        session.refresh(contract)
        session.refresh(invoice)

        session.add(ContractPermission(user_id=test_user.id, contract_id=contract.id, permission_level="read"))
        session.add(ContractPermission(user_id=test_user.id, contract_id=invoice.id, permission_level="read"))
        session.commit()

        response = auth_client.get("/contracts?document_type=invoice")

        assert response.status_code == 200
        assert [(item["title"], item["document_type"]) for item in response.json()] == [
            ("April Invoice", "invoice")
        ]


class TestContractSearch:
    """Test contract search and filtering."""
    
    def test_search_query_parameter(self, auth_client: TestClient):
        """Test search query parameter is accepted."""
        response = auth_client.get("/contracts?q=test")
        assert response.status_code == 200

    def test_search_query_filters_results(self, auth_client: TestClient, session, test_user):
        """Search should filter by title/description, not ignore the query."""
        first = Contract(title="Acme Master Agreement", file_path="uploads/acme.txt")
        second = Contract(title="Other Vendor", file_path="uploads/other.txt")
        session.add(first)
        session.add(second)
        session.commit()
        session.refresh(first)
        session.refresh(second)

        session.add(ContractPermission(user_id=test_user.id, contract_id=first.id, permission_level="read"))
        session.add(ContractPermission(user_id=test_user.id, contract_id=second.id, permission_level="read"))
        session.commit()

        response = auth_client.get("/contracts?q=Acme")

        assert response.status_code == 200
        assert [contract["title"] for contract in response.json()] == ["Acme Master Agreement"]
    
    def test_filter_by_tag(self, auth_client: TestClient):
        """Test filtering by tag."""
        response = auth_client.get("/contracts?tags=important")
        assert response.status_code == 200
    
    def test_sort_options(self, auth_client: TestClient):
        """Test sort options."""
        # Test valid sort options
        for sort_by in ["title", "value", "start_date", "end_date", "uploaded_at"]:
            response = auth_client.get(f"/contracts?sort_by={sort_by}")
            assert response.status_code == 200
        
        for sort_order in ["asc", "desc"]:
            response = auth_client.get(f"/contracts?sort_order={sort_order}")
            assert response.status_code == 200


class TestContractCRUD:
    """Test contract create, read, update, delete."""
    
    def test_create_contract_missing_file(self, auth_client: TestClient):
        """Test creating contract without file fails."""
        response = auth_client.post(
            "/contracts",
            data={
                "title": "Test Contract",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T23:59:59",
                "value": "1000.0"
            }
        )
        assert response.status_code == 422

    def test_create_contract_rejects_negative_value(self, auth_client: TestClient):
        """Form uploads should enforce the same schema constraints as JSON models."""
        response = auth_client.post(
            "/contracts",
            data={"title": "Invalid Contract", "value": "-1"},
            files={"file": ("contract.txt", b"hello", "text/plain")},
        )

        assert response.status_code == 422
    
    def test_get_nonexistent_contract(self, auth_client: TestClient):
        """Test getting a contract that doesn't exist."""
        response = auth_client.get("/contracts/99999/download")
        assert response.status_code == 404
    
    def test_delete_nonexistent_contract(self, auth_client: TestClient):
        """Test deleting a contract that doesn't exist."""
        response = auth_client.delete("/contracts/99999")
        assert response.status_code == 404
    
    def test_update_nonexistent_contract(self, auth_client: TestClient):
        """Test updating a contract that doesn't exist."""
        response = auth_client.put(
            "/contracts/99999",
            data={"title": "Updated Title"}
        )
        assert response.status_code == 404

    def test_delete_contract_writes_audit_log(self, auth_client: TestClient, session, test_user):
        """Deleting a contract should be visible in the audit trail."""
        contract = Contract(title="Delete Me", file_path="uploads/delete-me.pdf")
        session.add(contract)
        session.commit()
        session.refresh(contract)

        session.add(ContractPermission(user_id=test_user.id, contract_id=contract.id, permission_level="full"))
        session.commit()

        response = auth_client.delete(f"/contracts/{contract.id}")

        assert response.status_code == 204
        audit_log = session.exec(select(AuditLog).where(AuditLog.action == "DELETE_CONTRACT")).one()
        assert audit_log.user_id == test_user.id
        assert f"[CID:{contract.id}]" in audit_log.details

    def test_chat_rejects_non_pdf_contract_before_file_read(
        self,
        auth_client: TestClient,
        session,
        test_user,
        monkeypatch,
    ):
        """Contract chat should only accept files the AI path can process safely."""
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        contract = Contract(title="Text Contract", file_path="uploads/text-contract.txt")
        session.add(contract)
        session.commit()
        session.refresh(contract)

        session.add(ContractPermission(user_id=test_user.id, contract_id=contract.id, permission_level="read"))
        session.commit()

        response = auth_client.post(f"/contracts/{contract.id}/chat", json={"question": "Was steht drin?"})

        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]


class TestContractExport:
    """Test contract exports."""

    def test_export_uses_value_filter(self, auth_client: TestClient, session, test_user):
        low = Contract(title="Low Value", value=10, file_path="uploads/low.txt")
        high = Contract(title="High Value", value=500, file_path="uploads/high.txt")
        session.add(low)
        session.add(high)
        session.commit()
        session.refresh(low)
        session.refresh(high)

        session.add(ContractPermission(user_id=test_user.id, contract_id=low.id, permission_level="read"))
        session.add(ContractPermission(user_id=test_user.id, contract_id=high.id, permission_level="read"))
        session.commit()

        response = auth_client.get("/contracts/export?min_value=100&format=csv")
        body = response.content.decode("utf-8-sig")

        assert response.status_code == 200
        assert "High Value" in body
        assert "Low Value" not in body
