"""Drive explicitly started reviews on the server, including after a restart."""

import asyncio
import logging

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select, update

from models import DocumentReviewControl, DocumentReviewRun, User

logger = logging.getLogger("atlas.review")


async def drive_review(bind, run_id: str):
    from document_review import advance_review

    tasks = BackgroundTasks()
    try:
        with Session(bind) as session:
            # Serialize pause against claiming the next section. A pause arriving
            # after this transaction lets only the already claimed section finish.
            active = session.exec(update(DocumentReviewControl).where(
                col(DocumentReviewControl.run_id) == run_id,
                col(DocumentReviewControl.running).is_(True),
            ).values(running=True))
            if active.rowcount != 1:
                session.rollback()
                return
            run = session.get(DocumentReviewRun, run_id)
            user = session.exec(select(User).where(User.auth_subject == run.owner_subject)).first() if run else None
            if not user or not user.is_active:
                raise HTTPException(403, "Prüfung angehalten: Benutzerkonto nicht mehr aktiv.")
            result = advance_review(run_id, tasks, user, session)
            if result.get("finished"):
                session.exec(update(DocumentReviewControl).where(col(DocumentReviewControl.run_id) == run_id)
                             .values(running=False))
                session.commit()
                logger.info("Review run finished run=%s", run_id)
        await tasks()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - persist a safe run-level error
        # Never persist provider messages or raw exception text in run metadata.
        message = str(exc.detail) if isinstance(exc, HTTPException) else "Prüfsteuerung unterbrochen. Bitte Prüfung fortsetzen."
        logger.warning("Review dispatcher failed for %s (%s)", run_id, type(exc).__name__)
        with Session(bind) as session:
            session.exec(update(DocumentReviewControl).where(col(DocumentReviewControl.run_id) == run_id)
                         .values(running=False, error=message))
            session.commit()


async def dispatch_reviews(bind):
    jobs: dict[str, asyncio.Task] = {}
    logger.info("Review dispatcher started; checking for running reviews")
    try:
        while True:
            # A separate short transaction and task per run; no DB session is
            # held by the dispatcher while an OCR/model call is in flight.
            for key, job in list(jobs.items()):
                if job.done():
                    if not job.cancelled() and job.exception():
                        logger.warning("Review job %s stopped (%s)", key, type(job.exception()).__name__)
                    del jobs[key]
            try:
                with Session(bind) as session:
                    run_ids = session.exec(select(DocumentReviewControl.run_id).where(
                        col(DocumentReviewControl.running).is_(True),
                    )).all()
            except SQLAlchemyError:
                logger.warning("Review queue database unavailable; retrying")
                await asyncio.sleep(3)
                continue
            for run_id in run_ids:
                if run_id not in jobs or jobs[run_id].done():
                    jobs[run_id] = asyncio.create_task(drive_review(bind, run_id))
            await asyncio.sleep(1)
    finally:
        for job in jobs.values():
            job.cancel()
        await asyncio.gather(*jobs.values(), return_exceptions=True)
        logger.info("Review dispatcher stopped")
