"""Shared helpers for contract mutation endpoints."""

import os

from fastapi import HTTPException, Request
from limits import parse
from sqlalchemy.exc import IntegrityError
from slowapi.util import get_remote_address
from sqlmodel import Session, col, select

from api_core import limiter
from models import Tag

UPLOAD_RATE_LIMIT = os.getenv("RATE_LIMIT_UPLOAD", "20/hour")
UPLOAD_RATE_ITEM = parse(UPLOAD_RATE_LIMIT)


def enforce_upload_rate_limit(request: Request) -> None:
    """Consume one shared upload quota unit for the trusted client address."""
    client_address = get_remote_address(request)
    if not limiter.limiter.hit(
        UPLOAD_RATE_ITEM,
        client_address,
        "contract-upload",
    ):
        raise HTTPException(status_code=429, detail="Upload rate limit exceeded")


def resolve_tags(
    session: Session,
    tag_names: list[str],
    *,
    allow_create: bool = False,
) -> list[Tag]:
    """Resolve tags without committing the caller's transaction."""
    unique_names = list(dict.fromkeys(tag_names))
    if not unique_names:
        return []

    existing = session.exec(select(Tag).where(col(Tag.name).in_(unique_names))).all()
    tags_by_name = {tag.name: tag for tag in existing}
    missing_names = [name for name in unique_names if name not in tags_by_name]
    if missing_names and not allow_create:
        raise HTTPException(
            status_code=403,
            detail=(
                "Only administrators can create tags. Unknown tags: "
                + ", ".join(missing_names)
            ),
        )

    for tag_name in missing_names:
        try:
            with session.begin_nested():
                tag = Tag(name=tag_name)
                session.add(tag)
                session.flush()
            tags_by_name[tag_name] = tag
        except IntegrityError:
            tag = session.exec(select(Tag).where(Tag.name == tag_name)).first()
            if tag is None:
                raise
            tags_by_name[tag_name] = tag

    return [tags_by_name[name] for name in unique_names]
