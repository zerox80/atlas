"""
Test fixtures and configuration for backend tests.
"""
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from typing import Generator, AsyncGenerator

# Import the app and dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set SECRET_KEY for testing before importing main/auth
os.environ["SECRET_KEY"] = "test_secret_key_with_at_least_32_chars"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from main import app, get_current_user
from database import get_session
from models import User


# Create in-memory SQLite for testing
@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    """Create a test client with overridden dependencies."""
    
    def get_session_override():
        return session
    
    app.dependency_overrides[get_session] = get_session_override
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture(name="async_client")
async def async_client_fixture(session: Session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for testing async endpoints."""
    
    def get_session_override():
        return session
    
    app.dependency_overrides[get_session] = get_session_override
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture(name="test_user")
def test_user_fixture(session: Session) -> User:
    """Create a test user."""
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    user = User(
        username="testuser",
        hashed_password=pwd_context.hash("testpassword123"),
        role="user",
        is_active=True
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="admin_user")
def admin_user_fixture(session: Session) -> User:
    """Create an admin test user."""
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    user = User(
        username="admin",
        hashed_password=pwd_context.hash("adminpassword123"),
        role="admin",
        is_active=True
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="auth_client")
def auth_client_fixture(client: TestClient, test_user: User) -> TestClient:
    """Create an authenticated test client."""
    
    # Override get_current_user to return our test user
    def get_current_user_override():
        return test_user
    
    app.dependency_overrides[get_current_user] = get_current_user_override
    
    return client


@pytest.fixture(name="admin_client")
def admin_client_fixture(client: TestClient, admin_user: User) -> TestClient:
    """Create an authenticated admin test client."""
    
    def get_current_user_override():
        return admin_user
    
    app.dependency_overrides[get_current_user] = get_current_user_override
    
    return client
