"""Database models for users, contracts, lists, permissions, and audit logs."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# Join table for Contracts and Tags
class ContractTagLink(SQLModel, table=True):
    contract_id: Optional[int] = Field(default=None, foreign_key="contract.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)

class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    color: str = "#3b82f6" # Hex color
    
    contracts: List["Contract"] = Relationship(back_populates="tags", link_model=ContractTagLink)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    auth_subject: str = Field(
        default_factory=lambda: str(uuid4()),
        index=True,
        unique=True,
        nullable=False,
    )
    username: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = Field(default="user") # 'admin' or 'user'
    totp_secret: Optional[str] = None # Active 2FA secret
    pending_totp_secret: Optional[str] = None # Secret waiting for first OTP verification
    is_active: bool = Field(default=True)  # Account status managed through user editing
    # Incrementing this value invalidates every JWT issued with the previous value.
    token_version: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Permission levels: "read" = view only, "write" = edit, "full" = edit + delete
class ContractPermission(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "contract_id", name="uq_contractpermission_user_contract"),
        Index(
            "ix_contractpermission_user_level_contract",
            "user_id",
            "permission_level",
            "contract_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    contract_id: int = Field(foreign_key="contract.id", index=True)
    permission_level: str = Field(default="read")  # "read", "write", "full"


# Join table for Contracts and Lists
class ContractListLink(SQLModel, table=True):
    contract_id: Optional[int] = Field(default=None, foreign_key="contract.id", primary_key=True)
    list_id: Optional[int] = Field(default=None, foreign_key="contractlist.id", primary_key=True)


class ContractList(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    color: str = "#6366f1"  # Default indigo
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    contracts: List["Contract"] = Relationship(back_populates="lists", link_model=ContractListLink)

    
class Contract(SQLModel, table=True):
    __table_args__ = (
        Index("ix_contract_document_uploaded_at", "document_type", "uploaded_at"),
        Index("ix_contract_end_date", "end_date"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    file_path: str
    # Kept in the existing document table so permissions, tags and downloads work
    # consistently for both contracts and uploaded invoices.
    document_type: str = Field(default="contract", index=True)
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cancellation Logic
    notice_period: Optional[int] = Field(default=30, description="Notice period in days")
    
    # Financials
    value: float = Field(default=0.0)
    annual_value: Optional[float] = Field(default=None)
    
    # Status
    is_protected: bool = Field(default=False, description="Protected from deletion")
    
    # Versioning
    version: int = Field(default=1)
    parent_id: Optional[int] = Field(default=None, foreign_key="contract.id")
    
    # Relationships
    tags: List[Tag] = Relationship(back_populates="contracts", link_model=ContractTagLink)
    lists: List["ContractList"] = Relationship(back_populates="contracts", link_model=ContractListLink)
    
    # We could adding a children relationship for version history if needed
    # children: List["Contract"] = Relationship(sa_relationship_kwargs={"remote_side": "Contract.parent_id"})

    @property
    def file_extension(self) -> str:
        suffix = Path(self.file_path).suffix.lower() if self.file_path else ""
        return suffix or ".pdf"

class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    contract_id: Optional[int] = Field(default=None, index=True)
    action: str
    details: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
