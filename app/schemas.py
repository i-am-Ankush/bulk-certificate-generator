import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models import CertStatus, Certificate, Job, JobStatus

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class RecipientIn(BaseModel):
    """One recipient. Validated individually so one bad row never rejects the batch."""

    name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    achievement: str | None = Field(default=None, max_length=100)

    @field_validator("name", "achievement", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("achievement")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return v or None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        if v is not None and not EMAIL_RE.fullmatch(v):
            raise ValueError("must be a valid email address")
        return v


class JobCreate(BaseModel):
    """Request-level fields are strict (422). Recipients are validated one by one later."""

    event_title: str = Field(min_length=1, max_length=100)
    issued_by: str = Field(min_length=1, max_length=60)
    issue_date: date | None = None
    recipients: list[Any] = Field(min_length=1)

    @field_validator("event_title", "issued_by", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class JobOut(BaseModel):
    id: str
    event_title: str
    issued_by: str
    issue_date: date
    status: JobStatus
    total: int
    completed: int
    failed: int
    pending: int
    progress_percent: float
    created_at: datetime
    finished_at: datetime | None
    links: dict[str, str]

    @classmethod
    def from_job(cls, job: Job) -> "JobOut":
        done = job.completed + job.failed
        base = f"/api/jobs/{job.id}"
        return cls(
            id=job.id,
            event_title=job.event_title,
            issued_by=job.issued_by,
            issue_date=job.issue_date,
            status=job.status,
            total=job.total,
            completed=job.completed,
            failed=job.failed,
            pending=job.total - done,
            progress_percent=round(done / job.total * 100, 1) if job.total else 100.0,
            created_at=job.created_at,
            finished_at=job.finished_at,
            links={
                "self": f"{base}/",
                "certificates": f"{base}/certificates/",
                "download_all": f"{base}/download/",
            },
        )


class FailureOut(BaseModel):
    index: int
    recipient_name: str
    error: str | None


class JobDetail(JobOut):
    failures: list[FailureOut]


class CertificateOut(BaseModel):
    id: str
    index: int
    recipient_name: str
    recipient_email: str | None
    status: CertStatus
    error: str | None
    download_url: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_cert(cls, cert: Certificate) -> "CertificateOut":
        url = None
        if cert.status == CertStatus.COMPLETED:
            url = f"/api/jobs/{cert.job_id}/certificates/{cert.id}/download/"
        return cls(
            id=cert.id,
            index=cert.index,
            recipient_name=cert.recipient_name,
            recipient_email=cert.recipient_email,
            status=cert.status,
            error=cert.error,
            download_url=url,
            created_at=cert.created_at,
            completed_at=cert.completed_at,
        )


class CertificateList(BaseModel):
    count: int
    limit: int
    offset: int
    results: list[CertificateOut]
