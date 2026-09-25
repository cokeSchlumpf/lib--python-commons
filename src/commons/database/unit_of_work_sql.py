from typing import Callable, cast

from commons.users import SystemUser, User
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from .unit_of_work import CommitFunction, UnitOfWork, UnitOfWorkFactory


class SqlUnitOfWork[T](UnitOfWork[T]):
    """One ``Session`` and one transaction for a single ``with`` block.

    A **fresh instance per ``with``** (minted by :class:`SqlUnitOfWorkFactory`), so its
    session and audit actor are never shared between concurrent requests - ``commit`` and
    ``__exit__`` always act on this block's own session. ``__enter__`` opens the session
    and returns the repository bundle plus an async ``commit``; ``__exit__`` rolls back
    (if ``commit`` was never awaited) and closes.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        repositories_factory: Callable[[Session, User], T],
        *,
        user: User,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._user = user
        self._session: Session | None = None

    def __enter__(self) -> tuple[T, CommitFunction]:
        self._session = cast(Session, self._session_factory())

        return self._repositories_factory(self._session, self._user), self._commit

    def __exit__(self, *args: object) -> None:
        if self._session is not None:
            self._session.rollback()  # no-op once commit has flushed + committed
            self._session.close()
            self._session = None

    async def _commit(self) -> None:
        if self._session is not None:
            self._session.commit()


def _system_user() -> User:
    return SystemUser()


class SqlUnitOfWorkFactory[T](UnitOfWorkFactory[T]):
    """Mints a fresh :class:`SqlUnitOfWork` per ``with`` block.

    The factory is **stateless** and safe to share process-wide (it lives on the single
    composition root): ``for_user`` / ``for_system`` each return a new unit of work, so the
    object you enter is the object you exit. No per-request state lives on the shared
    instance, so concurrent requests cannot clobber each other's session or audit actor.

    Use ``with uow.for_user(user) as (repos, commit)`` so every history row is attributed;
    ``for_system()`` turns history off (bulk seeding). Entering the **factory itself** as a
    context manager resolves the actor via ``current_user_provider`` - inject one that reads
    your web framework's request context (the default attributes work to the system user).
    Keeping actor resolution injected is deliberate: it keeps this library free of any
    web-framework dependency.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        repositories_factory: Callable[[Session, User], T],
        current_user_provider: Callable[[], User] = _system_user,
    ) -> None:
        self._session_factory = session_factory
        self._repositories_factory = repositories_factory
        self._current_user_provider = current_user_provider
        self._current: SqlUnitOfWork[T] | None = None

    def _unit_of_work(self, *, user: User) -> SqlUnitOfWork[T]:
        return SqlUnitOfWork(self._session_factory, self._repositories_factory, user=user)

    def for_user(self, user: User) -> SqlUnitOfWork[T]:
        """A unit of work attributed to ``user`` (sets the history actor)."""
        return self._unit_of_work(user=user)

    def for_system(self) -> SqlUnitOfWork[T]:
        """A unit of work with history writing off (bulk seeding)."""
        return self._unit_of_work(user=SystemUser())

    def __enter__(self) -> tuple[T, CommitFunction]:
        self._current = self._unit_of_work(user=self._current_user_provider())
        return self._current.__enter__()

    def __exit__(self, *args: object) -> None:
        if self._current is not None:
            self._current.__exit__(*args)
            self._current = None
