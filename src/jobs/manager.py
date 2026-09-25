import logging
import runpy
import time
import traceback

from commons.datetime_operators import utc_now
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Thread, Event
from typing import Any, Iterator

from .job import JobStatus
from .jobs import JobsRepositoryPort


logger = logging.getLogger(__name__)


@dataclass
class JobUpdate:
    id: str

    progress: int

    last_update: datetime

    progress_message: str | None

    status: JobStatus

    result: dict[str, Any] | None

    error: str | None


@dataclass
class JobsUpdate:
    progress: int

    last_update: datetime

    progress_message: str | None

    running_count: int

    failed: int

    runtime: timedelta


class JobsManager:
    def __init__(
        self, jobs: JobsRepositoryPort, max_workers: int = 4, recover_running: bool = False, context: Any | None = None
    ) -> None:
        self.jobs = jobs
        self._max_workers = max_workers
        self._recover_running = recover_running
        self._executor: ThreadPoolExecutor | None = None
        self._poll_thread: Thread | None = None
        self._stop_event = Event()
        self._active_jobs: dict[str, Future] = {}  # job_id -> Future
        self._context = context

    def start(self) -> None:
        """Start the executor and polling thread."""
        if self._recover_running:
            self._recover_running_jobs()
        self._stop_event.clear()
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        self._poll_thread = Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("JobsManager started with %d workers", self._max_workers)

    def _recover_running_jobs(self) -> None:
        """Mark all running jobs as failed so they can be retried."""
        running_jobs = self.jobs.get_jobs(status="running")
        if running_jobs:
            logger.debug("Recovering %d running jobs on restart", len(running_jobs))
        for job in running_jobs:
            job.fail("Manager restarted - job recovered")

    def stop(self, wait: bool = True, timeout: float | None = None) -> None:
        """Stop the executor gracefully."""
        logger.info("JobsManager stopping")
        self._stop_event.set()
        if self._executor:
            self._executor.shutdown(wait=wait, cancel_futures=True)
        if self._poll_thread and timeout != 0:
            self._poll_thread.join(timeout=timeout)

    def subscribe(self, id: str, poll_interval: float = 0.5) -> Iterator[JobUpdate]:
        """
        Listen to updates of a job.

        The iterator will complete when processing of the job is done.

        Args:
            id: The id of the job to listen to.
            poll_interval: How often to poll for updates in seconds.
        """
        terminal_statuses = ("completed", "failed", "cancelled")
        last_update: datetime | None = None
        last_progress: int | None = None

        while True:
            job = self.jobs.find_job(id)
            if job is None:
                return  # Job not found or was removed

            # Yield if this is a new update
            if job.updated_at != last_update or job.progress != last_progress:
                last_update = job.updated_at
                last_progress = job.progress
                yield JobUpdate(
                    id=job.id,
                    progress=job.progress,
                    last_update=job.updated_at,
                    progress_message=job.progress_message,
                    status=job.status,
                    result=job.result,
                    error=job.error,
                )

            # Stop if terminal
            if job.status in terminal_statuses:
                return

            time.sleep(poll_interval)

    def subscribe_all(self, ids: list[str], poll_interval: float = 0.5) -> Iterator[JobsUpdate]:
        """
        Listen to updates from multiple jobs, yielding aggregated progress.

        The iterator will complete when all jobs reach a terminal status.

        Args:
            ids: List of job ids to subscribe to.
            poll_interval: How often to poll for updates in seconds.
        """
        if not ids:
            return

        terminal_statuses = ("completed", "failed", "cancelled")
        last_states: dict[str, tuple[datetime | None, int]] = {id: (None, -1) for id in ids}
        last_yield_time: float = 0
        time_update_interval: float = 5.0  # Yield at least every 5 seconds for runtime updates
        batch_start_time: datetime | None = None  # Track when first job started

        while True:
            jobs = [self.jobs.find_job(id) for id in ids]
            active_jobs = [j for j in jobs if j is not None]

            if not active_jobs:
                return  # All jobs removed

            # Check if any job has changed
            changed = False
            for job in active_jobs:
                last_update, last_progress = last_states.get(job.id, (None, -1))
                if job.updated_at != last_update or job.progress != last_progress:
                    last_states[job.id] = (job.updated_at, job.progress)
                    changed = True

            # Also yield periodically for runtime updates
            time_since_yield = time.monotonic() - last_yield_time
            should_yield = changed or time_since_yield >= time_update_interval

            if should_yield:
                # Calculate aggregates
                total_progress = sum(j.progress for j in active_jobs)
                progress = total_progress // len(active_jobs)

                # Find newest update and its message
                newest_job = max(active_jobs, key=lambda j: j.updated_at)
                last_update = newest_job.updated_at
                progress_message = newest_job.progress_message

                # Count failed jobs
                failed = sum(1 for j in active_jobs if j.status == "failed")

                # Calculate runtime from when first job in batch started
                if batch_start_time is None:
                    started_times = [j.started_at for j in active_jobs if j.started_at is not None]
                    if started_times:
                        batch_start_time = min(started_times)
                        if batch_start_time.tzinfo is None:
                            batch_start_time = batch_start_time.replace(tzinfo=timezone.utc)

                if batch_start_time is not None:
                    runtime = utc_now() - batch_start_time
                else:
                    runtime = timedelta(0)

                yield JobsUpdate(
                    progress=progress,
                    last_update=last_update,
                    progress_message=progress_message,
                    running_count=len(active_jobs),
                    failed=failed,
                    runtime=runtime,
                )
                last_yield_time = time.monotonic()

            # Stop if all jobs are terminal
            if all(j.status in terminal_statuses for j in active_jobs):
                return

            time.sleep(poll_interval)

    def _poll_loop(self) -> None:
        """Background thread that polls for pending and retryable jobs."""
        while not self._stop_event.is_set():
            self._process_pending_jobs()
            self._process_retryable_jobs()
            self._cleanup_expired_jobs()
            self._stop_event.wait(5.0)  # Poll interval

    def _process_pending_jobs(self) -> None:
        """Submit pending jobs to the executor (oldest first)."""
        pending = self.jobs.get_jobs(status="pending", order="created_asc")
        for job in pending:
            if len(self._active_jobs) >= self._max_workers:
                break
            if job.id not in self._active_jobs:
                self._submit_job(job.id)

    def _process_retryable_jobs(self) -> None:
        """Restart failed jobs that haven't exceeded max retries."""
        failed = self.jobs.get_jobs(status="failed", order="created_asc")
        for job in failed:
            if len(self._active_jobs) >= self._max_workers:
                break
            if job.id not in self._active_jobs and job.retries < job.max_retries:
                self._submit_job(job.id)

    def _cleanup_expired_jobs(self) -> None:
        """Remove jobs that have exceeded their retention period."""
        now = utc_now()
        for status in ("completed", "failed", "cancelled"):
            jobs = self.jobs.get_jobs(status=status)  # type: ignore
            for job in jobs:
                if job.completed_at is None:
                    continue
                # Ensure completed_at is timezone-aware (assume UTC if naive)
                completed_at = job.completed_at
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(tzinfo=timezone.utc)
                expiry_time = completed_at + timedelta(seconds=job.retention_seconds)
                if now > expiry_time:
                    logger.debug("Removing expired job %s (status=%s)", job.id, status)
                    job.remove()

    def _submit_job(self, job_id: str) -> None:
        """Submit a job to the thread pool."""
        assert self._executor is not None, "Executor not started"
        logger.info("Job %s submitted for execution", job_id)
        future = self._executor.submit(self._run_job, job_id)
        self._active_jobs[job_id] = future
        future.add_done_callback(lambda f: self._on_job_done(job_id, f))

    def _run_job(self, job_id: str) -> None:
        """Execute job in worker thread."""
        job = self.jobs.get_job(job_id)

        if job.status == "pending":
            job.start()
            logger.info("Job %s started", job_id)
        elif job.status == "failed":
            if job.retries >= job.max_retries:
                return
            job.restart()
            logger.info("Job %s restarted (retry %d/%d)", job_id, job.retries, job.max_retries)

        try:
            runpy.run_path(
                str(job.file), init_globals={"__JOB__": job, "__CONTEXT__": self._context}, run_name="__main__"
            )
        except Exception:
            if job.status == "running":  # Not already completed/failed
                error = traceback.format_exc()
                logger.error("Job %s failed with error: %s", job_id, error)
                job.fail(error)

    def _on_job_done(self, job_id: str, future: Future) -> None:
        """Cleanup when job finishes."""
        self._active_jobs.pop(job_id, None)
        exc = future.exception()
        if exc:
            error = "".join(traceback.format_exception(exc))
            logger.error("Job %s failed with exception: %s", job_id, error)
            job = self.jobs.find_job(job_id)
            if job and job.status == "running":
                job.fail(error)
        else:
            job = self.jobs.find_job(job_id)
            if job and job.status == "running":
                job.complete({})
                logger.info("Job %s auto-completed", job_id)
            else:
                logger.info("Job %s finished", job_id)
