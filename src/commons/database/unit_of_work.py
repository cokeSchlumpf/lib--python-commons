import abc
from typing import Awaitable, Callable

from commons.users import User

CommitFunction = Callable[[], Awaitable[None]]


class UnitOfWork[T](abc.ABC):
    """Port for a single transactional scope (one ``with`` block).

    Entering opens a transaction and returns the repository bundle plus a
    ``commit`` callable; leaving the block rolls back unless ``commit`` was
    awaited. Generic over ``T`` - the app-defined bundle of repositories the
    scope exposes.
    """

    @abc.abstractmethod
    def __enter__(self) -> tuple[T, CommitFunction]: ...

    @abc.abstractmethod
    def __exit__(self, *args) -> None: ...  # rolls back if not committed


class UnitOfWorkFactory[T](abc.ABC):
    """Port that mints a fresh :class:`UnitOfWork` per call - safe to share process-wide.

    ``for_user`` opens a unit of work attributed to the request user; ``for_system`` one
    attributed to the system user (background / bulk work). Each call yields its **own**
    session/scope, so concurrent requests never share transactional state or audit actor.
    The factory itself is not a context manager - always go through one of these methods so
    the object you enter is the object you exit.
    """

    @abc.abstractmethod
    def for_user(self, user: User) -> "UnitOfWork[T]":
        """Open a unit of work attributed to the request user (sets the audit actor)."""
        ...

    @abc.abstractmethod
    def for_system(self) -> "UnitOfWork[T]":
        """Open a unit of work with history writing off (bulk seeding)."""
        ...

    @abc.abstractmethod
    def __enter__(self) -> tuple[T, CommitFunction]: ...

    @abc.abstractmethod
    def __exit__(self, *args) -> None: ...  # rolls back if not committed
