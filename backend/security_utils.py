"""Security audit helpers shared by API routes."""

from datetime import datetime, timezone

from sqlmodel import Session

from models import AuditLog


def log_audit(
    session: Session,
    user_id: int | None,
    action: str,
    details: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    *,
    commit: bool = True,
) -> None:
    """Persist a single audit record in the caller's database session."""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        details=details,
        timestamp=datetime.now(timezone.utc),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(audit_log)
    if commit:
        session.commit()
