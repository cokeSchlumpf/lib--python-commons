import inspect
from typing import Any, TypeVar, overload

from .job import Job

T = TypeVar("T")


def _get_job() -> Job:
    """Look up __JOB__ from caller's globals (set by runpy.run_path)."""
    frame = inspect.currentframe()
    try:
        # Walk up the call stack to find __JOB__
        caller = frame.f_back.f_back if frame and frame.f_back else None
        while caller:
            job = caller.f_globals.get("__JOB__")
            if job is not None:
                return job
            caller = caller.f_back
        raise RuntimeError("__JOB__ not found in call stack. Are you running inside a job?")
    finally:
        del frame


def get_parameters() -> dict[str, Any]:
    """Get the job's input parameters."""
    return _get_job().parameters


def update_progress(progress: int, message: str | None = None) -> None:
    """Update the job's progress (0-100) with an optional message."""
    _get_job().update_progress(progress, message)


def fail(error: str) -> None:
    """Mark the job as failed with an error message."""
    _get_job().fail(error)


def complete(result: dict[str, Any]) -> None:
    """Mark the job as completed with a result dictionary."""
    _get_job().complete(result)


@overload
def get_context(type: type[T]) -> T: ...


@overload
def get_context(type: None = None) -> Any: ...


def get_context(type: type[T] | None = None) -> T | Any:
    """Get the context object from caller's globals (set by runpy.run_path).

    If a type is provided, validates that the context is an instance of that type
    and returns it with the correct type annotation.
    """
    frame = inspect.currentframe()
    try:
        caller = frame.f_back if frame else None
        while caller:
            context = caller.f_globals.get("__CONTEXT__")
            if context is not None:
                if type is not None:
                    # Compare by fully-qualified name instead of isinstance()
                    # to handle runpy.run_path() module namespace issues
                    expected = f"{type.__module__}.{type.__qualname__}"
                    actual = f"{context.__class__.__module__}.{context.__class__.__qualname__}"
                    if expected != actual:
                        raise TypeError(
                            f"Context is not an instance of {type.__name__}, got {context.__class__.__name__}"
                        )
                return context
            caller = caller.f_back
        raise RuntimeError("__CONTEXT__ not found in call stack. Are you running inside a job with context?")
    finally:
        del frame
