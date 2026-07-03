from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
import re

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_username_pattern(v: str) -> str:
    if not USERNAME_PATTERN.match(v):
        raise ValueError('Username must contain only letters, numbers, underscores, and hyphens')
    return v


class Token(BaseModel):
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('username')
    @classmethod
    def username_pattern(cls, v: str) -> str:
        return validate_username_pattern(v)

class TagRead(BaseModel):
    id: int
    name: str
    color: str


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field(default="#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class ContractListRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str
    created_at: datetime
    contract_count: int = 0

    class Config:
        from_attributes = True

class ContractCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    value: Optional[float] = Field(default=None, ge=0)
    annual_value: Optional[float] = Field(default=None, ge=0)
    tags: List[str] = Field(default_factory=list)
    notice_period: Optional[int] = Field(default=30, ge=0, description="Notice period in days")

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError('Title must not be blank')
        return cleaned

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, values: List[str]) -> List[str]:
        return normalize_tag_names(values)

class ContractUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    value: Optional[float] = Field(None, ge=0)
    annual_value: Optional[float] = Field(None, ge=0)
    tags: Optional[List[str]] = None
    notice_period: Optional[int] = Field(None, ge=0)

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = v.strip()
        if not cleaned:
            raise ValueError('Title must not be blank')
        return cleaned

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        if values is None:
            return None
        return normalize_tag_names(values)

class ContractRead(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # file_path removed - internal server path should not be exposed!
    uploaded_at: datetime
    value: Optional[float] = None
    annual_value: Optional[float] = None
    version: int
    tags: List[TagRead] = []
    lists: List[ContractListRead] = []
    notice_period: Optional[int] = None
    is_protected: bool
    file_extension: str
    can_read: bool = True
    can_write: bool = False
    can_delete: bool = False
    can_manage_protection: bool = False

    class Config:
        from_attributes = True


class AuditLogRead(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str] = None
    action: str
    details: str
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class OTPVerify(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6)


# Admin Panel Schemas
class UserRead(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    has_2fa: bool = False

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=32)
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None

    @field_validator('username')
    @classmethod
    def username_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return validate_username_pattern(v)


class PermissionCreate(BaseModel):
    user_id: int
    contract_id: int
    permission_level: str = Field(default="read", pattern="^(read|write|full)$")


class PermissionRead(BaseModel):
    id: int
    user_id: int
    contract_id: int
    permission_level: str
    username: Optional[str] = None
    contract_title: Optional[str] = None

    class Config:
        from_attributes = True


# Contract List Schemas
class ContractListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class ContractListUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


# AI Feature Schemas
class ContractAnalysisResult(BaseModel):
    """Result from AI contract analysis."""
    title: Optional[str] = None
    description: Optional[str] = None
    value: Optional[float] = None
    annual_value: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notice_period: Optional[int] = None
    tags: List[str] = []


class ChatRequest(BaseModel):
    """Request body for contract chat."""
    question: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """Response from contract chat."""
    answer: str


def normalize_tag_names(values: List[str]) -> List[str]:
    """Trim, deduplicate, and enforce tag name bounds."""
    normalized: List[str] = []
    seen = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if len(cleaned) > 50:
            raise ValueError('Tag names must be at most 50 characters')
        if cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)
    return normalized
