import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"  # accepted, waiting for the worker
    PROCESSING = "PROCESSING"  # worker is generating certificates
    COMPLETED = "COMPLETED"  # every recipient succeeded
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"  # some succeeded, some failed
    FAILED = "FAILED"  # nothing could be generated


class CertStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_title: Mapped[str] = mapped_column(String(200))
    issued_by: Mapped[str] = mapped_column(String(200))
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32), default=JobStatus.PENDING
    )
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="job",
        order_by="Certificate.index",
        cascade="all, delete-orphan",
    )


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    index: Mapped[int] = mapped_column(Integer)  # 1-based position in the request
    recipient_name: Mapped[str] = mapped_column(String(255))
    recipient_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    achievement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[CertStatus] = mapped_column(
        Enum(CertStatus, native_enum=False, length=32), default=CertStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job: Mapped[Job] = relationship(back_populates="certificates")
