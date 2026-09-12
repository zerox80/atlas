"""Database models for users, contracts, lists, permissions, and audit logs."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


# Join table for Contracts and Tags
class ContractTagLink(SQLModel, table=True):
    contract_id: int | None = Field(default=None, foreign_key="contract.id", primary_key=True)
    tag_id: int | None = Field(default=None, foreign_key="tag.id", primary_key=True)

class Tag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    color: str = "#3b82f6" # Hex color
    
    contracts: list["Contract"] = Relationship(back_populates="tags", link_model=ContractTagLink)

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    auth_subject: str = Field(
        default_factory=lambda: str(uuid4()),
        index=True,
        unique=True,
        nullable=False,
    )
    username: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = Field(default="user") # 'admin' or 'user'
    totp_secret: str | None = None # Active 2FA secret
    pending_totp_secret: str | None = None # Secret waiting for first OTP verification
    is_active: bool = Field(default=True)  # Account status managed through user editing
    # Incrementing this value invalidates every JWT issued with the previous value.
    token_version: int = Field(default=0, nullable=False)
    # Per-account admin view preference. It never changes permissions.
    show_other_user_workspaces: bool = Field(default=True, nullable=False)
    # Admin-selected upload target. This is intentionally separate from
    # workspace permissions: granting access must never change where uploads go.
    default_workspace_id: int | None = Field(
        default=None,
        foreign_key="contractlist.id",
        index=True,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )


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

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    contract_id: int = Field(foreign_key="contract.id", index=True)
    permission_level: str = Field(default="read")  # "read", "write", "full"


# Join table for Contracts and Lists
class ContractListLink(SQLModel, table=True):
    contract_id: int | None = Field(default=None, foreign_key="contract.id", primary_key=True)
    list_id: int | None = Field(default=None, foreign_key="contractlist.id", primary_key=True)


class ContractList(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    name: str = Field(index=True)
    description: str | None = None
    color: str = "#6366f1"  # Default indigo
    is_default: bool = Field(default=False, nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    
    contracts: list["Contract"] = Relationship(back_populates="lists", link_model=ContractListLink)


# A workspace permission applies to every document linked to the collection.
class ContractListPermission(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "list_id",
            name="uq_contractlistpermission_user_list",
        ),
        Index(
            "ix_contractlistpermission_user_level_list",
            "user_id",
            "permission_level",
            "list_id",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    list_id: int = Field(foreign_key="contractlist.id", index=True)
    permission_level: str = Field(default="read")  # "read", "write", "full"

    
class Contract(SQLModel, table=True):
    __table_args__ = (
        Index("ix_contract_document_uploaded_at", "document_type", "uploaded_at"),
        Index("ix_contract_end_date", "end_date"),
        Index("ix_contract_deleted_at", "deleted_at"),
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    title: str
    description: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    file_path: str
    # Kept in the existing document table so permissions, tags and downloads work
    # consistently for both contracts and uploaded invoices.
    document_type: str = Field(default="contract", index=True)
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Documents stay linked to their workspaces while they are in the trash so
    # every workspace has its own recoverable view of deleted content.
    deleted_at: datetime | None = None
    deleted_by_user_id: int | None = Field(default=None, foreign_key="user.id")
    
    # Cancellation Logic
    notice_period: int | None = Field(default=30, description="Notice period in days")
    
    # Financials
    value: float = Field(default=0.0)
    annual_value: float | None = Field(default=None)
    
    # Status
    is_protected: bool = Field(default=False, description="Protected from deletion")
    
    # Versioning
    version: int = Field(default=1)
    parent_id: int | None = Field(default=None, foreign_key="contract.id")
    
    # Relationships
    tags: list[Tag] = Relationship(back_populates="contracts", link_model=ContractTagLink)
    lists: list["ContractList"] = Relationship(back_populates="contracts", link_model=ContractListLink)
    
    # We could adding a children relationship for version history if needed
    # children: List["Contract"] = Relationship(sa_relationship_kwargs={"remote_side": "Contract.parent_id"})

    @property
    def file_extension(self) -> str:
        suffix = Path(self.file_path).suffix.lower() if self.file_path else ""
        return suffix or ".pdf"


class PendingFileDeletion(SQLModel, table=True):
    """Durable outbox entry for removing a document file after DB commit."""

    __table_args__ = (
        UniqueConstraint(
            "file_path",
            name="uq_pendingfiledeletion_file_path",
        ),
        Index(
            "ix_pendingfiledeletion_created_at",
            "created_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    file_path: str
    attempts: int = Field(default=0, nullable=False)
    last_error: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="user.id")
    contract_id: int | None = Field(default=None, index=True)
    document_history_visible: bool = Field(default=True)
    action: str
    details: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ip_address: str | None = None
    user_agent: str | None = None
