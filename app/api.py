import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import service
from app.models import Certificate, CertStatus, Job, JobStatus
from app.schemas import (
    CertificateList,
    CertificateOut,
    FailureOut,
    JobCreate,
    JobDetail,
    JobOut,
)

router = APIRouter(prefix="/api", tags=["jobs"])


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def _get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/", response_model=JobOut, status_code=202)
def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    session: Session = Depends(get_session),
):
    """Submit many recipients in one request. Returns immediately; poll the job."""
    settings = request.app.state.settings
    if len(payload.recipients) > settings.max_recipients:
        raise HTTPException(
            422, f"At most {settings.max_recipients} recipients are allowed per job"
        )
    job = service.create_job(session, payload)
    if job.status == JobStatus.PENDING:
        background_tasks.add_task(
            service.process_job,
            request.app.state.session_factory,
            settings.storage_dir,
            job.id,
        )
    return JobOut.from_job(job)


@router.get("/jobs/{job_id}/", response_model=JobDetail)
def get_job(job_id: str, session: Session = Depends(get_session)):
    """Progress, counts and the list of failed recipients with reasons."""
    job = _get_job(session, job_id)
    failed = session.scalars(
        select(Certificate)
        .where(Certificate.job_id == job_id, Certificate.status == CertStatus.FAILED)
        .order_by(Certificate.index)
    ).all()
    return JobDetail(
        **JobOut.from_job(job).model_dump(),
        failures=[
            FailureOut(index=c.index, recipient_name=c.recipient_name, error=c.error)
            for c in failed
        ],
    )


@router.get("/jobs/{job_id}/certificates/", response_model=CertificateList)
def list_certificates(
    job_id: str,
    status: CertStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    _get_job(session, job_id)
    query = select(Certificate).where(Certificate.job_id == job_id)
    if status:
        query = query.where(Certificate.status == status)
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Certificate.index).limit(limit).offset(offset)).all()
    return CertificateList(
        count=count,
        limit=limit,
        offset=offset,
        results=[CertificateOut.from_cert(c) for c in rows],
    )


def _certificate_file(request: Request, cert: Certificate) -> Path:
    path = request.app.state.settings.storage_dir / cert.file_path
    if not path.is_file():
        raise HTTPException(404, "Certificate file is missing from storage")
    return path


@router.get("/jobs/{job_id}/certificates/{certificate_id}/download/")
def download_certificate(
    job_id: str,
    certificate_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    _get_job(session, job_id)
    cert = session.get(Certificate, certificate_id)
    if cert is None or cert.job_id != job_id:
        raise HTTPException(404, "Certificate not found")
    if cert.status != CertStatus.COMPLETED:
        raise HTTPException(409, f"Certificate is {cert.status.value}; no file available")
    return FileResponse(
        _certificate_file(request, cert),
        media_type="application/pdf",
        filename=Path(cert.file_path).name,
    )


@router.get("/jobs/{job_id}/download/")
def download_all(job_id: str, request: Request, session: Session = Depends(get_session)):
    """ZIP of every certificate generated so far (works for partially finished jobs)."""
    _get_job(session, job_id)
    certs = session.scalars(
        select(Certificate)
        .where(Certificate.job_id == job_id, Certificate.status == CertStatus.COMPLETED)
        .order_by(Certificate.index)
    ).all()
    if not certs:
        raise HTTPException(409, "No certificates have been generated for this job yet")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as archive:
        for cert in certs:
            archive.write(_certificate_file(request, cert), arcname=Path(cert.file_path).name)
    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"certificates_{job_id}.zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )
