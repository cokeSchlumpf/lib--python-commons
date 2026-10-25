"""
SQL storage of login requests, shared by several processes.
"""

from datetime import UTC, datetime

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, SQLModel, col  # type: ignore

from commons.users.login_tokens.model import LoginTokenRequest
from commons.users.login_tokens.store import LoginTokenStore


class LoginTokenRequestRow(SQLModel, table=True):
    """
    Table row of a login request (internal to ``SQLLoginTokenStore``).

    Times are stored as naive UTC: not every database keeps time zones
    (SQLite doesn't), and naive UTC compares the same everywhere.
    """

    __tablename__ = "login_token_requests"  # type: ignore

    id: str = Field(primary_key=True, max_length=64)
    user_id: str = Field(max_length=64)
    email_hash: str = Field(index=True, max_length=64)
    link_hash: str = Field(index=True, unique=True, max_length=64)
    code_hash: str = Field(max_length=64)
    created_at: datetime = Field(index=True)
    expires_at: datetime = Field(index=True)
    redirect_to: str | None = Field(default=None, max_length=2048)
    failed_attempts: int = Field(default=0)
    consumed_at: datetime | None = Field(default=None)


def _to_db(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _from_db(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)


def _to_row(request: LoginTokenRequest) -> LoginTokenRequestRow:
    return LoginTokenRequestRow(
        id=request.id,
        user_id=request.user_id,
        email_hash=request.email_hash,
        link_hash=request.link_hash,
        code_hash=request.code_hash,
        created_at=_to_db(request.created_at),
        expires_at=_to_db(request.expires_at),
        redirect_to=request.redirect_to,
        failed_attempts=request.failed_attempts,
        consumed_at=_to_db(request.consumed_at) if request.consumed_at else None,
    )


def _from_row(row: LoginTokenRequestRow) -> LoginTokenRequest:
    return LoginTokenRequest(
        id=row.id,
        user_id=row.user_id,
        email_hash=row.email_hash,
        link_hash=row.link_hash,
        code_hash=row.code_hash,
        created_at=_from_db(row.created_at),
        expires_at=_from_db(row.expires_at),
        redirect_to=row.redirect_to,
        failed_attempts=row.failed_attempts,
        consumed_at=_from_db(row.consumed_at) if row.consumed_at else None,
    )


class SQLLoginTokenStore(LoginTokenStore):
    """
    Keeps login requests in the ``login_token_requests`` table.

    Use it when the app runs several processes or workers: they all see the
    same requests (a link sent by one worker works on every other) and
    share the rate limits. Creates its table on initialization if it
    doesn't exist.

    Args:
        engine: SQLAlchemy Engine connected to the database.

    Example::

        from sqlalchemy import create_engine
        from commons.users.login_tokens import SQLLoginTokenStore

        store = SQLLoginTokenStore(create_engine("sqlite:///app.db"))
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._create_session = sessionmaker(bind=self._engine)

        SQLModel.metadata.create_all(
            self._engine,
            tables=[LoginTokenRequestRow.__table__],  # type: ignore[attr-defined]
            checkfirst=True,
        )

    def add(self, request: LoginTokenRequest) -> None:
        with self._create_session() as session:
            session.add(_to_row(request))
            session.commit()

    def get(self, request_id: str) -> LoginTokenRequest | None:
        with self._create_session() as session:
            row = session.get(LoginTokenRequestRow, request_id)
            return _from_row(row) if row else None

    def find_by_link_hash(self, link_hash: str) -> LoginTokenRequest | None:
        with self._create_session() as session:
            row = session.execute(
                select(LoginTokenRequestRow).where(LoginTokenRequestRow.link_hash == link_hash)  # type: ignore[arg-type]
            ).scalar_one_or_none()
            return _from_row(row) if row else None

    def consume(self, request_id: str, now: datetime) -> bool:
        # A single conditional UPDATE: the database guarantees that only one
        # of two concurrent calls changes the row.
        db_now = _to_db(now)
        with self._create_session() as session:
            result = session.execute(
                update(LoginTokenRequestRow)
                .where(
                    LoginTokenRequestRow.id == request_id,  # type: ignore[arg-type]
                    LoginTokenRequestRow.consumed_at.is_(None),  # type: ignore[union-attr]
                    LoginTokenRequestRow.expires_at > db_now,  # type: ignore[arg-type]
                )
                .values(consumed_at=db_now)
            )
            session.commit()
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def record_failed_attempt(self, request_id: str) -> int:
        with self._create_session() as session:
            session.execute(
                update(LoginTokenRequestRow)
                .where(LoginTokenRequestRow.id == request_id)  # type: ignore[arg-type]
                .values(failed_attempts=LoginTokenRequestRow.failed_attempts + 1)
            )
            session.commit()
            attempts = session.execute(
                select(col(LoginTokenRequestRow.failed_attempts)).where(
                    LoginTokenRequestRow.id == request_id  # type: ignore[arg-type]
                )
            ).scalar_one_or_none()
            return attempts or 0

    def count_requests(self, *, email_hash: str, since: datetime) -> int:
        query = (
            select(func.count())
            .select_from(LoginTokenRequestRow)
            .where(
                LoginTokenRequestRow.email_hash == email_hash,  # type: ignore[arg-type]
                LoginTokenRequestRow.created_at >= _to_db(since),  # type: ignore[arg-type]
            )
        )

        with self._create_session() as session:
            return session.execute(query).scalar_one()

    def delete_expired(self, before: datetime) -> int:
        with self._create_session() as session:
            rows = (
                session.execute(
                    select(LoginTokenRequestRow).where(LoginTokenRequestRow.expires_at < _to_db(before))  # type: ignore[arg-type]
                )
                .scalars()
                .all()
            )
            for row in rows:
                session.delete(row)
            session.commit()
            return len(rows)
