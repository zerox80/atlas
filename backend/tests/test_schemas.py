"""
Tests for Pydantic schemas and validation.
"""
import pytest
from pydantic import ValidationError
from datetime import datetime

# Add parent directory to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import (
    UserCreate, 
    UserUpdate,
    TagCreate, 
    TagUpdate,
    ContractCreate, 
    ContractUpdate,
    ContractListCreate,
    OTPVerify
)


class TestUserCreateSchema:
    """Test UserCreate schema validation."""
    
    def test_valid_user(self):
        """Test valid user creation."""
        user = UserCreate(username="validuser", password="validpassword123")
        assert user.username == "validuser"
    
    def test_username_too_short(self):
        """Test username minimum length."""
        with pytest.raises(ValidationError):
            UserCreate(username="ab", password="validpassword123")
    
    def test_username_too_long(self):
        """Test username maximum length."""
        with pytest.raises(ValidationError):
            UserCreate(username="a" * 33, password="validpassword123")
    
    def test_password_too_short(self):
        """Test password minimum length."""
        with pytest.raises(ValidationError):
            UserCreate(username="validuser", password="short")
    
    def test_username_invalid_characters(self):
        """Test username with invalid characters."""
        with pytest.raises(ValidationError):
            UserCreate(username="user@name!", password="validpassword123")
    
    def test_username_valid_characters(self):
        """Test username with valid special characters."""
        user = UserCreate(username="user_name-123", password="validpassword123")
        assert user.username == "user_name-123"


class TestUserUpdateSchema:
    """Test UserUpdate schema validation."""

    def test_username_invalid_characters(self):
        """User updates should enforce the same username pattern as creation."""
        with pytest.raises(ValidationError):
            UserUpdate(username="user@name!")

    def test_username_valid_characters(self):
        """Test user update with valid special characters."""
        user = UserUpdate(username="user_name-123")
        assert user.username == "user_name-123"


class TestTagSchemas:
    """Test tag-related schemas."""
    
    def test_valid_tag_create(self):
        """Test valid tag creation."""
        tag = TagCreate(name="Important", color="#ff0000")
        assert tag.name == "Important"
        assert tag.color == "#ff0000"
    
    def test_tag_create_default_color(self):
        """Test tag creation with default color."""
        tag = TagCreate(name="Test")
        assert tag.color == "#3b82f6"  # Default blue
    
    def test_tag_name_too_long(self):
        """Test tag name maximum length."""
        with pytest.raises(ValidationError):
            TagCreate(name="a" * 51)  # Max 50
    
    def test_tag_invalid_color(self):
        """Test invalid color format."""
        with pytest.raises(ValidationError):
            TagCreate(name="Test", color="red")
    
    def test_tag_invalid_color_short(self):
        """Test short hex color (should be 6 chars)."""
        with pytest.raises(ValidationError):
            TagCreate(name="Test", color="#fff")
    
    def test_tag_update_partial(self):
        """Test partial tag update."""
        tag = TagUpdate(name="NewName")
        assert tag.name == "NewName"
        assert tag.color is None


class TestContractSchemas:
    """Test contract-related schemas."""
    
    def test_valid_contract_create(self):
        """Test valid contract creation."""
        contract = ContractCreate(
            title="Test Contract",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            value=1000.0
        )
        assert contract.title == "Test Contract"
        assert contract.value == 1000.0
    
    def test_contract_title_too_long(self):
        """Test contract title maximum length."""
        with pytest.raises(ValidationError):
            ContractCreate(
                title="a" * 256,  # Max 255
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 12, 31)
            )
    
    def test_contract_negative_value(self):
        """Test contract value cannot be negative."""
        with pytest.raises(ValidationError):
            ContractCreate(
                title="Test",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 12, 31),
                value=-100.0
            )
    
    def test_contract_update_partial(self):
        """Test partial contract update."""
        update = ContractUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.value is None


class TestContractListSchemas:
    """Test contract list schemas."""
    
    def test_valid_list_create(self):
        """Test valid list creation."""
        lst = ContractListCreate(
            name="My List",
            description="Test description",
            color="#6366f1"
        )
        assert lst.name == "My List"
    
    def test_list_name_too_long(self):
        """Test list name maximum length."""
        with pytest.raises(ValidationError):
            ContractListCreate(name="a" * 101)  # Max 100


class TestOTPSchema:
    """Test OTP verification schema."""
    
    def test_valid_otp(self):
        """Test valid 6-digit OTP."""
        otp = OTPVerify(otp="123456")
        assert otp.otp == "123456"
    
    def test_otp_too_short(self):
        """Test OTP too short."""
        with pytest.raises(ValidationError):
            OTPVerify(otp="12345")
    
    def test_otp_too_long(self):
        """Test OTP too long."""
        with pytest.raises(ValidationError):
            OTPVerify(otp="1234567")
