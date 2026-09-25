import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import DateTime, Engine, Integer, String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
    sessionmaker,
)

from commons.database_operators import create_engine

from .job import Job, JobStatus
from .jobs import JobOrder, JobsRepositoryPort


class Base(MappedAsDataclass, DeclarativeBase):
    pass


class JobPE(Base):
    """Persistence entity for Job."""

    __tablename__ = "jobs"

    # Fields without defaults (required)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(String(256))
    file: Mapped[str] = mapped_column(String)
    created: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    no_progress_timeout_seconds: Mapped[int] = mapped_column(Integer)
    retention_seconds: Mapped[int] = mapped_column(Integer)
    max_retries: Mapped[int] = mapped_column(Integer)
    retry_timeout_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)

    # Fields with defaults
    parameters_json: Mapped[str] = mapped_column(String, default="{}")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(String, default="{}")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    progress_message: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)


class SQLJob(Job):
    """SQL implementation of Job."""

    def __init__(self, engine: Engine, job_pe: JobPE) -> None:
        self._engine = engine
        self._create_session = sessionmaker(bind=self._engine)
        self._id = job_pe.id
        self._type = job_pe.type
        self._name = job_pe.name
        self._title = job_pe.title
        self._file = job_pe.file
        self._parameters_json = job_pe.parameters_json
        self._created = job_pe.created
        self._started_at = job_pe.started_at
        self._completed_at = job_pe.completed_at
        self._updated_at = job_pe.updated_at
        self._no_progress_timeout_seconds = job_pe.no_progress_timeout_seconds
        self._retention_seconds = job_pe.retention_seconds
        self._max_retries = job_pe.max_retries
        self._retry_timeout_seconds = job_pe.retry_timeout_seconds
        self._progress = job_pe.progress
        self._progress_message = job_pe.progress_message
        self._status = job_pe.status
        self._retries = job_pe.retries
        self._result_json = job_pe.result_json
        self._error = job_pe.error

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return self._type

    @property
    def name(self) -> str:
        return self._name

    @property
    def title(self) -> str:
        return self._title

    @property
    def file(self) -> Path:
        return Path(self._file)

    @property
    def parameters(self) -> dict[str, Any]:
        return json.loads(self._parameters_json)

    @property
    def created(self) -> datetime:
        return self._created

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def completed_at(self) -> datetime | None:
        return self._completed_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def no_progres_timeout_seconds(self) -> int:
        return self._no_progress_timeout_seconds

    @property
    def retention_seconds(self) -> int:
        return self._retention_seconds

    @property
    def progress(self) -> int:
        return self._progress

    @property
    def progress_message(self) -> str | None:
        return self._progress_message

    @property
    def status(self) -> JobStatus:
        return self._status  # type: ignore

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def retries(self) -> int:
        return self._retries

    @property
    def retry_timeout_seconds(self) -> int:
        return self._retry_timeout_seconds

    @property
    def result(self) -> dict[str, Any] | None:
        if self._result_json:
            return json.loads(self._result_json)
        return None

    @property
    def error(self) -> str | None:
        return self._error

    def _update(
        self,
        updated_at: datetime,
        started_at: datetime | None,
        completed_at: datetime | None,
        status: JobStatus,
        progress: int,
        progress_message: str | None,
        result: dict[str, Any] | None,
        error: str | None,
        retries: int,
    ) -> None:
        with self._create_session() as s:
            job_pe = s.query(JobPE).filter(JobPE.id == self._id).first()

            if job_pe:
                job_pe.updated_at = updated_at
                job_pe.started_at = started_at
                job_pe.completed_at = completed_at
                job_pe.status = status
                job_pe.progress = progress
                job_pe.progress_message = progress_message
                job_pe.result_json = json.dumps(result) if result is not None else "{}"
                job_pe.error = error
                job_pe.retries = retries

                s.merge(job_pe)
                s.commit()

                # Update local state
                self._updated_at = updated_at
                self._started_at = started_at
                self._completed_at = completed_at
                self._status = status
                self._progress = progress
                self._progress_message = progress_message
                self._result_json = job_pe.result_json
                self._error = error
                self._retries = retries

    def remove(self) -> None:
        with self._create_session() as s:
            job_pe = s.query(JobPE).filter(JobPE.id == self._id).first()
            if job_pe:
                s.delete(job_pe)
                s.commit()


class SQLJobsRepository(JobsRepositoryPort):
    """SQL implementation of JobsRepositoryPort."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        Base.metadata.create_all(self._engine)
        self._create_session = sessionmaker(bind=self._engine)

    @staticmethod
    def create_from_settings() -> "SQLJobsRepository":
        return SQLJobsRepository(create_engine())

    def find_job(self, id: str) -> Job | None:
        with self._create_session() as s:
            job_pe = s.query(JobPE).filter(JobPE.id == id).first()

            if job_pe:
                return SQLJob(self._engine, job_pe)
            return None

    def get_jobs(
        self,
        type: str | None = None,
        status: JobStatus | None = None,
        name: str | None = None,
        order: JobOrder = "created_desc",
    ) -> list[Job]:
        with self._create_session() as s:
            query = s.query(JobPE)

            if type is not None:
                query = query.filter(JobPE.type == type)

            if status is not None:
                query = query.filter(JobPE.status == status)

            if name is not None:
                query = query.filter(JobPE.name == name)

            if order == "created_asc":
                query = query.order_by(JobPE.created.asc())
            else:
                query = query.order_by(JobPE.created.desc())

            return [SQLJob(self._engine, job_pe) for job_pe in query.all()]

    def _create_job(
        self,
        *,
        file: Path,
        id: str,
        type: str,
        name: str,
        title: str,
        parameters: dict[str, Any],
        no_progres_timeout_seconds: int,
        retention_seconds: int,
        max_retries: int,
        retry_timeout_seconds: int,
        created: datetime,
        started_at: datetime | None,
        completed_at: datetime | None,
        updated_at: datetime | None,
        progress: int,
        progress_message: str | None,
        status: JobStatus,
        retries: int,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> Job:
        with self._create_session() as s:
            job_pe = JobPE(
                id=id,
                type=type,
                name=name,
                title=title,
                file=str(file),
                parameters_json=json.dumps(parameters),
                created=created,
                started_at=started_at,
                completed_at=completed_at,
                updated_at=updated_at or created,
                no_progress_timeout_seconds=no_progres_timeout_seconds,
                retention_seconds=retention_seconds,
                max_retries=max_retries,
                retry_timeout_seconds=retry_timeout_seconds,
                progress=progress,
                progress_message=progress_message,
                status=status,
                retries=retries,
                result_json=json.dumps(result),
                error=error,
            )

            s.add(job_pe)
            s.commit()

            return SQLJob(self._engine, job_pe)
