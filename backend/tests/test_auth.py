"""
Tests for authentication endpoints.
"""
from fastapi.testclient import TestClient
import pyotp
from sqlmodel import select

from auth import get_password_hash, verify_password
from main import bootstrap_admin_user
from models import AuditLog, Contract, ContractPermission, User


class TestAuthentication:
    """Test authentication flows."""
    
    def test_login_success(self, client: TestClient, test_user):
        """Test successful login."""
        response = client.post(
            "/token",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert "access_token" not in data
        assert "access_token" in response.cookies
        assert "csrf_token" in response.cookies
    
    def test_login_wrong_password(self, client: TestClient, test_user):
        """Test login with wrong password."""
        response = client.post(
            "/token",
            data={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
    
    def test_login_nonexistent_user(self, client: TestClient):
        """Test login with non-existent user."""
        response = client.post(
            "/token",
            data={
                "username": "nonexistent",
                "password": "somepassword"
            }
        )
        assert response.status_code == 401
    
    def test_logout(self, auth_client: TestClient):
        """Test logout clears cookie."""
        response = auth_client.post("/logout")
        assert response.status_code == 200
        # Cookie is cleared by setting max_age=0
        assert "access_token" in response.cookies or response.status_code == 200

    def test_cookie_authenticated_mutation_requires_csrf_token(self, client: TestClient):
        """Cookie-authenticated mutations require a matching CSRF header."""
        client.cookies.set("access_token", "jwt-present")

        response = client.post("/logout")

        assert response.status_code == 403

    def test_cookie_authenticated_mutation_accepts_matching_csrf_token(self, client: TestClient):
        """CSRF double-submit token allows cookie-authenticated mutations."""
        client.cookies.set("access_token", "jwt-present")
        client.cookies.set("csrf_token", "csrf-test-token")

        response = client.post("/logout", headers={"X-CSRF-Token": "csrf-test-token"})

        assert response.status_code == 200
    
    def test_protected_route_without_auth(self, client: TestClient):
        """Test that protected routes require authentication."""
        response = client.get("/contracts")
        assert response.status_code == 401

    def test_setup_2fa_requires_successful_verification_before_enabling(
        self,
        auth_client: TestClient,
        session,
        test_user: User,
    ):
        """2FA setup must not lock users out before the first OTP is verified."""
        response = auth_client.post(
            "/2fa/setup",
            json={"password": "testpassword123"},
        )

        assert response.status_code == 200
        session.refresh(test_user)
        assert test_user.totp_secret is None
        assert test_user.pending_totp_secret

        otp = pyotp.TOTP(test_user.pending_totp_secret).now()
        response = auth_client.post("/2fa/verify", json={"otp": otp})

        assert response.status_code == 200
        session.refresh(test_user)
        assert test_user.totp_secret
        assert test_user.pending_totp_secret is None

    def test_setup_2fa_requires_current_password(self, auth_client: TestClient):
        response = auth_client.post(
            "/2fa/setup",
            json={"password": "wrong-password"},
        )

        assert response.status_code == 401


class TestUserCreation:
    """Test user registration."""
    
    def test_create_user_invalid_username_short(self, admin_client: TestClient):
        """Test username validation - too short."""
        response = admin_client.post(
            "/admin/users",
            json={
                "username": "ab",  # Too short (min 3)
                "password": "validpassword123"
            }
        )
        assert response.status_code == 422
    
    def test_create_user_invalid_password_short(self, admin_client: TestClient):
        """Test password validation - too short."""
        response = admin_client.post(
            "/admin/users",
            json={
                "username": "validuser",
                "password": "short"  # Too short (min 8)
            }
        )
        assert response.status_code == 422
    
    def test_create_user_invalid_username_chars(self, admin_client: TestClient):
        """Test username with invalid characters."""
        response = admin_client.post(
            "/admin/users",
            json={
                "username": "user@name!",  # Invalid chars
                "password": "validpassword123"
            }
        )
        assert response.status_code == 422


class TestAdminBootstrap:
    """Test first-run admin bootstrap behavior."""

    def test_existing_admin_password_is_not_reset(self, session, monkeypatch):
        """ADMIN_PASSWORD bootstraps only missing admins and never overwrites users."""
        admin = User(
            username="admin",
            hashed_password=get_password_hash("old-password-123"),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)

        monkeypatch.setenv("ADMIN_PASSWORD", "new-password-123")
        bootstrap_admin_user(session)
        session.refresh(admin)

        assert verify_password("old-password-123", admin.hashed_password)
        assert not verify_password("new-password-123", admin.hashed_password)


class TestAdminSafety:
    """Test admin account safety rails."""

    def test_cannot_demote_self(self, admin_client: TestClient, admin_user: User):
        response = admin_client.put(
            f"/admin/users/{admin_user.id}",
            json={"role": "user"},
        )

        assert response.status_code == 400

    def test_cannot_deactivate_self_via_update(
        self,
        admin_client: TestClient,
        admin_user: User,
    ):
        response = admin_client.put(
            f"/admin/users/{admin_user.id}",
            json={"is_active": False},
        )

        assert response.status_code == 400

    def test_cannot_delete_self(
        self,
        admin_client: TestClient,
        admin_user: User,
    ):
        response = admin_client.delete(f"/admin/users/{admin_user.id}")

        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot delete yourself"

    def test_cannot_delete_last_active_admin(
        self,
        admin_client: TestClient,
        admin_user: User,
        session,
    ):
        admin_user.is_active = False
        last_active_admin = User(
            username="last-admin",
            hashed_password=get_password_hash("last-admin-password"),
            role="admin",
            is_active=True,
        )
        session.add(admin_user)
        session.add(last_active_admin)
        session.commit()
        session.refresh(last_active_admin)

        response = admin_client.delete(f"/admin/users/{last_active_admin.id}")

        assert response.status_code == 400
        assert response.json()["detail"] == "At least one active admin must remain"
        assert session.get(User, last_active_admin.id) is not None


class TestUserDeletion:
    """Test permanent deletion through the admin endpoint."""

    def test_delete_user_removes_permissions_and_preserves_audit_history(
        self,
        admin_client: TestClient,
        admin_user: User,
        session,
    ):
        user = User(
            username="delete-me",
            hashed_password=get_password_hash("delete-me-password"),
            role="user",
            is_active=True,
        )
        contract = Contract(title="Deletion test", file_path="deletion-test.pdf")
        session.add(user)
        session.add(contract)
        session.commit()
        session.refresh(user)
        session.refresh(contract)
        user_id = user.id

        permission = ContractPermission(
            user_id=user_id,
            contract_id=contract.id,
            permission_level="read",
        )
        historical_log = AuditLog(
            user_id=user_id,
            action="LOGIN",
            details="User logged in",
        )
        session.add(permission)
        session.add(historical_log)
        session.commit()
        session.refresh(historical_log)

        response = admin_client.delete(f"/admin/users/{user_id}")

        assert response.status_code == 204
        assert session.exec(
            select(User).where(User.username == "delete-me")
        ).first() is None
        assert session.exec(
            select(ContractPermission).where(ContractPermission.user_id == user_id)
        ).all() == []

        session.refresh(historical_log)
        assert historical_log.user_id is None
        assert historical_log.details == "User logged in"

        deletion_log = session.exec(
            select(AuditLog).where(AuditLog.action == "DELETE_USER")
        ).one()
        assert deletion_log.user_id == admin_user.id
        assert deletion_log.details == "Deleted user 'delete-me'"

        users_response = admin_client.get("/admin/users")
        assert users_response.status_code == 200
        assert all(item["username"] != "delete-me" for item in users_response.json())

        recreate_response = admin_client.post(
            "/admin/users",
            json={
                "username": "delete-me",
                "password": "new-password-123",
            },
        )
        assert recreate_response.status_code == 200
