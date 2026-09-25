from abc import ABC, abstractmethod
from commons.string_operators import random_name
from commons.datetime_operators import utc_now
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from .job import Job, JobStatus


JobOrder = Literal["created_asc", "created_desc"]


class JobsRepositoryPort(ABC):
    @abstractmethod
    def find_job(self, id: str) -> Job | None: ...

    def get_job(self, id: str) -> Job:
        job = self.find_job(id)
        assert job is not None, f"No job with id `{id}`"
        return job

    @abstractmethod
    def get_jobs(
        self,
        type: str | None = None,
        status: JobStatus | None = None,
        name: str | None = None,
        order: JobOrder = "created_desc",
    ) -> list[Job]: ...

    def create(
        self,
        *,
        file: Path,
        id: str | None = None,
        type: str = "job",
        name: str | None = None,
        title: str | None = None,
        parameters: dict[str, Any] | None = None,
        no_progres_timeout_seconds: int = 60 * 5,
        retention_seconds: int = 60 * 60 * 24,
        max_retries: int = 0,
        retry_timeout_seconds: int = 60,
    ) -> Job:
        if id is None:
            id = str(uuid4())

        if name is None:
            name = random_name([job.name for job in self.get_jobs()])

        if title is None:
            title = name

        if parameters is None:
            parameters = {}

        return self._create_job(
            file=file,
            id=id,
            type=type,
            name=name,
            title=title,
            parameters=parameters,
            no_progres_timeout_seconds=no_progres_timeout_seconds,
            retention_seconds=retention_seconds,
            max_retries=max_retries,
            retry_timeout_seconds=retry_timeout_seconds,
            created=utc_now(),
            started_at=None,
            completed_at=None,
            updated_at=utc_now(),
            progress=0,
            progress_message=None,
            status="pending",
            retries=0,
            result=None,
            error=None,
        )

    @abstractmethod
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
    ) -> Job: ...
