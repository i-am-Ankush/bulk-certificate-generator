"""Job creation and background processing."""
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import pdf
from app.models import Certificate, CertStatus, Job, JobStatus, utcnow
from app.schemas import JobCreate, RecipientIn

logger = logging.getLogger(__name__)


def _format_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "recipient"
        parts.append(f"{loc}: {err['msg'].removeprefix('Value error, ')}")
    return "; ".join(parts)


def _display_name(raw: Any) -> str:
    if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"].strip():
        return raw["name"].strip()[:255]
    return "(unnamed)"


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:40] or "certificate"


def create_job(session: Session, payload: JobCreate) -> Job:
    """Validate every recipient and persist the job.

    Valid recipients become PENDING certificates. Invalid ones are stored as FAILED
    with the reason, so the client sees them in the job status and the rest proceed.
    """
    job = Job(
        event_title=payload.event_title,
        issued_by=payload.issued_by,
        issue_date=payload.issue_date or date.today(),
        status=JobStatus.PENDING,
        total=len(payload.recipients),
        completed=0,
        failed=0,
    )
    for index, raw in enumerate(payload.recipients, start=1):
        try:
            recipient = RecipientIn.model_validate(raw)
        except ValidationError as exc:
            job.certificates.append(
                Certificate(
                    index=index,
                    recipient_name=_display_name(raw),
                    status=CertStatus.FAILED,
                    error=_format_errors(exc),
                    completed_at=utcnow(),
                )
            )
            job.failed += 1
        else:
            job.certificates.append(
                Certificate(
                    index=index,
                    recipient_name=recipient.name,
                    recipient_email=recipient.email,
                    achievement=recipient.achievement,
                    status=CertStatus.PENDING,
                )
            )

    if job.failed == job.total:  # nothing valid to generate
        job.status = JobStatus.FAILED
        job.finished_at = utcnow()

    session.add(job)
    session.commit()
    return job


def _process_certificate(session: Session, job: Job, cert: Certificate, storage_dir: Path) -> None:
    relative = Path(job.id) / f"{cert.index:05d}_{_slug(cert.recipient_name)}.pdf"
    target = storage_dir / relative
    try:
        pdf.render_certificate(
            target,
            pdf.CertificateData(
                recipient_name=cert.recipient_name,
                event_title=job.event_title,
                issued_by=job.issued_by,
                issue_date=job.issue_date,
                achievement=cert.achievement,
            ),
        )
    except Exception as exc:  # isolate: one bad certificate must not stop the job
        logger.warning("Certificate %s (job %s) failed: %s", cert.index, job.id, exc)
        target.unlink(missing_ok=True)
        cert.status = CertStatus.FAILED
        cert.error = str(exc)[:500] or exc.__class__.__name__
        job.failed += 1
    else:
        cert.status = CertStatus.COMPLETED
        cert.file_path = relative.as_posix()
        job.completed += 1
    cert.completed_at = utcnow()
    session.commit()  # commit per certificate so progress is visible while running


def process_job(session_factory: sessionmaker, storage_dir: Path, job_id: str) -> None:
    """Generate every PENDING certificate of a job. Runs in the background."""
    with session_factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        try:
            job.status = JobStatus.PROCESSING
            session.commit()

            pending_ids = session.scalars(
                select(Certificate.id)
                .where(Certificate.job_id == job_id, Certificate.status == CertStatus.PENDING)
                .order_by(Certificate.index)
            ).all()
            for cert_id in pending_ids:
                cert = session.get(Certificate, cert_id)
                _process_certificate(session, job, cert, storage_dir)

            if job.failed == 0:
                job.status = JobStatus.COMPLETED
            elif job.completed == 0:
                job.status = JobStatus.FAILED
            else:
                job.status = JobStatus.COMPLETED_WITH_ERRORS
            job.finished_at = utcnow()
            session.commit()
        except Exception:
            # Infrastructure-level failure (DB, disk). Don't leave the job stuck.
            logger.exception("Job %s crashed", job_id)
            session.rollback()
            job = session.get(Job, job_id)
            job.status = JobStatus.FAILED
            job.finished_at = utcnow()
            session.commit()
