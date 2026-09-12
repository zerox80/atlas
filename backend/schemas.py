import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_FINANCIAL_VALUE = 1_000_000_000_000_000.0
MAX_CONTRACT_TAGS = 50
MAX_NOTICE_PERIOD_DAYS = 36_500


def validate_username_pattern(v: str) -> str:
    if not USERNAME_PATTERN.match(v):
        raise ValueError('Username must contain only letters, numbers, underscores, and hyphens')
    return v


class Token(BaseModel):
    token_type: str

class TokenData(BaseModel):
    auth_subject: str | None = None

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('username')
    @classmethod
    def username_pattern(cls, v: str) -> str:
        return validate_username_pattern(v)


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field(default="#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class ContractListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_user_id: int | None = None
    owner_username: str | None = None
    name: str
    description: str | None = None
    color: str
    is_default: bool = False
    created_at: datetime
    contract_count: int = 0
    can_read: bool = True
    can_write: bool = False
    is_preferred_default: bool = False


class ContractCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    start_date: datetime | None = None
    end_date: datetime | None = None
    value: float | None = Field(default=None, ge=0, le=MAX_FINANCIAL_VALUE, allow_inf_nan=False)
    annual_value: float | None = Field(default=None, ge=0, le=MAX_FINANCIAL_VALUE, allow_inf_nan=False)
    tags: list[str] = Field(default_factory=list, max_length=MAX_CONTRACT_TAGS)
    notice_period: int | None = Field(default=30, ge=0, le=MAX_NOTICE_PERIOD_DAYS, description="Notice period in days")
    document_type: Literal["contract", "invoice"] = "contract"

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError('Title must not be blank')
        return cleaned

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return normalize_tag_names(values)

class ContractUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    start_date: datetime | None = None
    end_date: datetime | None = None
    value: float | None = Field(None, ge=0, le=MAX_FINANCIAL_VALUE, allow_inf_nan=False)
    annual_value: float | None = Field(None, ge=0, le=MAX_FINANCIAL_VALUE, allow_inf_nan=False)
    tags: list[str] | None = Field(default=None, max_length=MAX_CONTRACT_TAGS)
    notice_period: int | None = Field(None, ge=0, le=MAX_NOTICE_PERIOD_DAYS)

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = v.strip()
        if not cleaned:
            raise ValueError('Title must not be blank')
        return cleaned

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return normalize_tag_names(values)

class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    # file_path removed - internal server path should not be exposed!
    uploaded_at: datetime
    value: float | None = None
    annual_value: float | None = None
    version: int
    tags: list[TagRead] = Field(default_factory=list)
    lists: list[ContractListRead] = Field(default_factory=list)
    notice_period: int | None = None
    is_protected: bool
    file_extension: str
    document_type: Literal["contract", "invoice"] = "contract"
    business_timezone: str = "Europe/Berlin"
    can_read: bool = True
    can_write: bool = False
    can_delete: bool = False
    can_manage_protection: bool = False


class TrashDocumentRead(ContractRead):
    deleted_at: datetime
    deleted_by_user_id: int | None = None
    deleted_by_username: str | None = None


class TrashDocumentPage(BaseModel):
    items: list[TrashDocumentRead]
    total: int
    offset: int
    limit: int


class AuditLogRead(BaseModel):
    id: int
    user_id: int | None
    username: str | None = None
    action: str
    details: str
    timestamp: datetime
    ip_address: str | None = None
    user_agent: str | None = None


class ContractAuditLogRead(BaseModel):
    id: int
    user_id: int | None
    username: str | None = None
    action: str
    details: str
    timestamp: datetime


class ContractAuditLogPage(BaseModel):
    items: list[ContractAuditLogRead]
    has_more: bool
    next_cursor_timestamp: datetime | None = None
    next_cursor_id: int | None = None


class OTPVerify(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6)

    @field_validator("otp")
    @classmethod
    def otp_is_numeric(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("OTP must contain only digits")
        return value


class TwoFactorSetup(BaseModel):
    """Proof required before issuing a new TOTP enrollment secret."""

    password: str = Field(..., min_length=8, max_length=128)
    current_otp: str | None = Field(default=None, min_length=6, max_length=6)

    @field_validator("current_otp")
    @classmethod
    def current_otp_is_numeric(cls, value: str | None) -> str | None:
        if value is not None and not value.isdigit():
            raise ValueError("OTP must contain only digits")
        return value


# Admin Panel Schemas
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    has_2fa: bool = False
    default_workspace_id: int | None = None
    default_workspace_name: str | None = None
    show_other_user_workspaces: bool = True


class AdminWorkspaceVisibilityUpdate(BaseModel):
    show_other_user_workspaces: bool


class AdminWorkspaceVisibilityRead(BaseModel):
    show_other_user_workspaces: bool


class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=32)
    password: str | None = Field(None, min_length=8, max_length=128)
    role: str | None = Field(None, pattern="^(admin|user)$")
    is_active: bool | None = None
    default_workspace_id: int | None = Field(None, ge=1)

    @field_validator('username')
    @classmethod
    def username_pattern(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_username_pattern(v)


class UserPasswordUpdate(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)


class PermissionCreate(BaseModel):
    user_id: int
    contract_id: int
    permission_level: str = Field(default="read", pattern="^(read|write|full)$")


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    scope_type: Literal["document", "workspace"] = "document"
    contract_id: int | None = None
    list_id: int | None = None
    permission_level: str
    username: str | None = None
    contract_title: str | None = None
    list_name: str | None = None
    target_name: str | None = None


class WorkspacePermissionCreate(BaseModel):
    user_id: int
    list_id: int
    permission_level: str = Field(default="read", pattern="^(read|write|full)$")


class DefaultWorkspaceUpdate(BaseModel):
    list_id: int | None = None


class DefaultWorkspaceOptionRead(BaseModel):
    id: int
    name: str
    owner_user_id: int | None = None
    owner_username: str | None = None
    is_personal: bool = False
    requires_write_grant: bool = False


class PermissionPage(BaseModel):
    items: list[PermissionRead]
    total: int
    offset: int
    limit: int


# Contract List Schemas
class ContractListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class ContractListUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class ContractSelection(BaseModel):
    contract_ids: list[Annotated[int, Field(gt=0)]] = Field(
        ...,
        min_length=1,
        max_length=10_000,
    )

    @field_validator("contract_ids")
    @classmethod
    def deduplicate_contract_ids(cls, values: list[int]) -> list[int]:
        return list(dict.fromkeys(values))


class ContractListBulkUpdate(ContractSelection):
    operation: Literal["add", "remove"]


class ContractListAssignmentRead(BaseModel):
    contract_id: int
    list_ids: list[int]


class ContractListBulkResult(BaseModel):
    operation: Literal["add", "remove", "move_to_default"]
    changed_count: int
    assignments: list[ContractListAssignmentRead]


class ContractProtectionBulkResult(BaseModel):
    changed_count: int
    already_protected_count: int


# AI Feature Schemas
class ContractAnalysisResult(BaseModel):
    """Result from AI contract analysis."""
    title: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=2000)
    value: float | None = Field(
        None, ge=0, le=MAX_FINANCIAL_VALUE, allow_inf_nan=False
    )
    annual_value: float | None = Field(
        None, ge=0, le=MAX_FINANCIAL_VALUE, allow_inf_nan=False
    )
    start_date: str | None = Field(None, max_length=64)
    end_date: str | None = Field(None, max_length=64)
    notice_period: int | None = Field(None, ge=0, le=MAX_NOTICE_PERIOD_DAYS)
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list,
        max_length=MAX_CONTRACT_TAGS,
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def dates_are_iso8601(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Date suggestions must use ISO 8601") from error
        return value

    @field_validator("tags")
    @classmethod
    def normalize_analysis_tags(cls, values: list[str]) -> list[str]:
        return normalize_tag_names(values)


class ChatRequest(BaseModel):
    """Request body for contract chat."""
    question: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """Response from contract chat."""
    answer: str


def normalize_tag_names(values: list[str]) -> list[str]:
    """Trim, deduplicate, and enforce tag name bounds."""
    normalized: list[str] = []
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
