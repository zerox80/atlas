"""Durable post-commit cleanup for uploaded document files."""

import logging

from sqlmodel import Session, col, select

from file_utils import delete_upload_file_or_raise
from models import PendingFileDeletion

logger = logging.getLogger(__name__)
MAX_CLEANUP_ERROR_LENGTH = 1_000


def enqueue_file_deletion(
    session: Session,
    file_path: str | None,
) -> PendingFileDeletion | None:
    """Persist a cleanup job in the caller's document-deletion transaction."""
    if not file_path:
        return None

    existing_job = session.exec(
        select(PendingFileDeletion).where(
            col(PendingFileDeletion.file_path) == file_path
        )
    ).first()
    if existing_job is not None:
        return existing_job

    job = PendingFileDeletion(file_path=file_path)
    session.add(job)
    session.flush()
    return job


def process_file_deletion_job(session: Session, job_id: int) -> bool:
    """Try one queued deletion and retain failures for a later retry."""
    job = session.get(PendingFileDeletion, job_id)
    if job is None:
        return True

    try:
        delete_upload_file_or_raise(job.file_path)
    except OSError as error:
        job.attempts += 1
        job.last_error = str(error)[:MAX_CLEANUP_ERROR_LENGTH]
        session.add(job)
        session.commit()
        logger.warning(
            "Upload cleanup remains queued after attempt %s for %s: %s",
            job.attempts,
            job.file_path,
            error,
        )
        return False

    session.delete(job)
    session.commit()
    return True


def process_pending_file_deletions(session: Session) -> tuple[int, int]:
    """Retry every durable cleanup job, returning success/failure counts."""
    job_ids = list(
        session.exec(
            select(col(PendingFileDeletion.id))
            .where(col(PendingFileDeletion.id).is_not(None))
            .order_by(
                col(PendingFileDeletion.created_at),
                col(PendingFileDeletion.id),
            )
        ).all()
    )
    deleted_count = 0
    failed_count = 0
    for job_id in job_ids:
        if job_id is None:
            continue
        if process_file_deletion_job(session, job_id):
            deleted_count += 1
        else:
            failed_count += 1
    return deleted_count, failed_count