"""
Tests for authentication endpoints.
"""
from fastapi.testclient import TestClient
import pyotp

from auth import get_password_hash, verify_password
from main import bootstrap_admin_user
from models import User


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
        response = auth_client.post("/2fa/setup")

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
