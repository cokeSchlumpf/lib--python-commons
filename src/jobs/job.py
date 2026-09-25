from abc import ABC, abstractmethod
from commons import datetime_operators
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class Job(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """The unique id of the job."""

    @property
    @abstractmethod
    def type(self) -> str:
        """A category of the job. To allow applications to distinguish between different process types."""

    @property
    @abstractmethod
    def name(self) -> str:
        """A unique technical name for the job."""

    @property
    @abstractmethod
    def title(self) -> str:
        """A human-readable title which might be shown to the end-user."""

    @property
    @abstractmethod
    def file(self) -> Path:
        """A Python file which defines the actual job logic."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Serialized set of input parameters for the job."""

    @property
    @abstractmethod
    def created(self) -> datetime:
        """The datetime when the job has been created (UTC)."""

    @property
    @abstractmethod
    def started_at(self) -> datetime | None:
        """The dateime when the job has been started."""

    @property
    @abstractmethod
    def completed_at(self) -> datetime | None:
        """The datetime when the job was last updated."""

    @property
    @abstractmethod
    def updated_at(self) -> datetime:
        """The datetime when the job was last updated."""

    @property
    @abstractmethod
    def no_progres_timeout_seconds(self) -> int:
        """
        The time in seconds the job should be considered as stale when no update has been recorded.
        When this timeout is reached, the job process will be killed and it will be restarted.
        """

    @property
    @abstractmethod
    def retention_seconds(self) -> int:
        """Time in seconds the job should be kept in database after completion before automatic deletion."""

    @property
    @abstractmethod
    def progress(self) -> int:
        """The progress as percent value (0 - 100)."""

    @property
    @abstractmethod
    def progress_message(self) -> str | None:
        """A message (for users) which describes the current progress."""

    @property
    @abstractmethod
    def status(self) -> JobStatus:
        """The status of the job."""

    @property
    @abstractmethod
    def max_retries(self) -> int:
        """The number of maximum retries for the job."""

    @property
    @abstractmethod
    def retries(self) -> int:
        """Number of current retry attempts."""

    @property
    @abstractmethod
    def retry_timeout_seconds(self) -> int:
        """The retry timeout in seconds."""

    @property
    @abstractmethod
    def result(self) -> dict[str, Any] | None:
        """A serialized result of the job."""

    @property
    @abstractmethod
    def error(self) -> str | None:
        """If job has failed, this property will contain the error message."""

    def update_progress(self, progress: int, progress_message: str | None = None) -> None:
        """Updates the job's progress."""

        self._update(
            updated_at=datetime_operators.utc_now(),
            progress=min(100, max(0, progress)),
            progress_message=progress_message,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=self.status,
            result=self.result,
            error=self.error,
            retries=self.retries,
        )

    def start(self) -> None:
        """Starts the job."""
        self._update(
            updated_at=datetime_operators.utc_now(),
            started_at=datetime_operators.utc_now(),
            status="running",
            completed_at=self.completed_at,
            progress=0,
            progress_message=None,
            result={},
            error=None,
            retries=self.retries,
        )

    def cancel(self) -> None:
        """Cancels the job."""

        self._update(
            updated_at=datetime_operators.utc_now(),
            completed_at=datetime_operators.utc_now(),
            status="cancelled",
            started_at=self.started_at,
            progress=100,
            progress_message=None,
            result=self.result,
            error=None,
            retries=self.retries,
        )

    def complete(self, result: dict[str, Any]) -> None:
        """Completes the job."""

        self._update(
            updated_at=datetime_operators.utc_now(),
            completed_at=datetime_operators.utc_now(),
            status="completed",
            result=result,
            started_at=self.started_at,
            progress=100,
            progress_message=None,
            error=None,
            retries=self.retries,
        )

    def fail(self, error: str) -> None:
        """Sets the job into failed state."""

        self._update(
            updated_at=datetime_operators.utc_now(),
            completed_at=datetime_operators.utc_now(),
            status="failed",
            error=error,
            started_at=self.started_at,
            progress=self.progress,
            progress_message=self.progress_message,
            result=self.result,
            retries=self.retries,
        )

    def restart(self) -> None:
        """Restarts the job."""

        self._update(
            updated_at=datetime_operators.utc_now(),
            started_at=datetime_operators.utc_now(),
            status="running",
            retries=self.retries + 1,
            completed_at=self.completed_at,
            progress=0,
            progress_message=None,
            result={},
            error=None,
        )

    @abstractmethod
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
        """Internal update method."""

    @abstractmethod
    def remove(self) -> None:
        """Remove the job from the repository."""
