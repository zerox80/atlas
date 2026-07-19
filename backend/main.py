"""FastAPI application assembly for Atlas."""

import logging
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select
from starlette.background import BackgroundTask

from admin_routes import router as admin_router
from ai_routes import router as ai_router
from api_core import (
    CSRF_COOKIE_NAME,
    CSRF_EXEMPT_PATHS,
    CSRF_HEADER_NAME,
    backfill_existing_contract_read_permissions,
    bootstrap_admin_user,
    get_current_user,
    limiter,
    require_admin,
)
from auth_routes import router as auth_router
from backup_export import cleanup_backup_file, create_document_backup
from catalog_routes import router as catalog_router
from contract_queries import router as contract_query_router
from contract_routes import router as contract_router
from database import create_db_and_tables, get_session
from list_routes import router as list_router
from migrate_db import get_default_db_path, migrate
from models import Contract, Tag, User
from security_utils import log_audit

__all__ = [
    "app",
    "backfill_existing_contract_read_permissions",
    "bootstrap_admin_user",
    "get_current_user",
]

app = FastAPI()
logger = logging.getLogger(__name__)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # type: ignore[arg-type]
)

cors_allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost,http://localhost:80,http://127.0.0.1,http://127.0.0.1:80",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    """Require a double-submit CSRF token for cookie-authenticated mutations."""
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path not in CSRF_EXEMPT_PATHS
        and request.cookies.get("access_token")
    ):
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        csrf_header = request.headers.get(CSRF_HEADER_NAME)
        if (
            not csrf_cookie
            or not csrf_header
            or not secrets.compare_digest(csrf_cookie, csrf_header)
        ):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid or missing CSRF token"},
            )

    return await call_next(request)


@app.on_event("startup")
def on_startup():
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/ze_dashboard.db")
    if database_url.startswith("sqlite:///"):
        database_path = get_default_db_path()
        # A genuinely fresh database needs the current tables before the
        # migration ledger can backfill indexes. Existing schemas must migrate
        # before create_all sees columns introduced by those migrations.
        if not os.path.exists(database_path) or os.path.getsize(database_path) == 0:
            create_db_and_tables()
        migrate(database_path)
    create_db_and_tables()
    with next(get_session()) as session:
        bootstrap_admin_user(session)

        if not session.exec(select(Tag)).first():
            tags = [
                Tag(name="Software", color="#3b82f6"),
                Tag(name="Hardware", color="#ef4444"),
                Tag(name="Legal", color="#10b981"),
                Tag(name="HR", color="#f59e0b"),
            ]
            for tag in tags:
                session.add(tag)
            session.commit()

        backfill_existing_contract_read_permissions(session)


@app.post("/admin/backup")
def create_admin_document_backup(
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Download every contract and invoice, including protected documents."""
    backup = None
    try:
        documents = session.exec(
            select(Contract)
            .where(col(Contract.document_type).in_(["contract", "invoice"]))
            .options(selectinload(Contract.tags), selectinload(Contract.lists))  # type: ignore[arg-type]
            .order_by(col(Contract.document_type), col(Contract.id))
        ).all()
        backup = create_document_backup(documents)

        log_audit(
            session,
            admin.id,
            "ADMIN_DOCUMENT_BACKUP",
            (
                f"contracts={backup.contract_count}; invoices={backup.invoice_count}; "
                f"exported_files={backup.attachment_count}; "
                f"missing_files={backup.missing_attachment_count}"
            ),
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
        )
    except Exception as error:
        if backup is not None:
            cleanup_backup_file(backup.path)
        logger.exception("Admin document backup failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datensicherung konnte nicht erstellt werden",
        ) from error

    return FileResponse(
        path=backup.path,
        media_type="application/zip",
        filename=backup.filename,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(cleanup_backup_file, backup.path),
    )



app.include_router(auth_router)
app.include_router(contract_query_router)
app.include_router(contract_router)
app.include_router(catalog_router)
app.include_router(admin_router)
app.include_router(list_router)
app.include_router(ai_router)
