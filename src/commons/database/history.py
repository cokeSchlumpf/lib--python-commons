from collections.abc import Sequence
from datetime import datetime
from typing import Self

from commons.datetime_operators import utc_now
from commons.string_operators import pluralize, to_snake_case
from commons.users import User
from sqlalchemy import Index, false, or_, text
from sqlalchemy.orm import declared_attr
from sqlmodel import Field, Session, SQLModel, col, select

from .column_lengths import ID_LENGTH, NAME_LENGTH
from .entity import EntityMixin
from .types import UTCDateTime


def _history_tablename(class_name: str) -> str:
    """``CountryHistoryORM`` -> ``countries-history`` (pluralise the entity, then re-tag as history)."""
    entity = class_name.removesuffix("ORM").removesuffix("History")
    return f"{pluralize(to_snake_case(entity))}_history"


class HistoryMixin[E: EntityMixin](SQLModel):
    """Base for a history table, generic over the entity ORM ``E`` it mirrors (``HistoryMixin[CountryORM]``).

    Inheriting it (with ``table=True``) derives the table name from the class and adds the open-interval
    index — both via ``declared_attr`` so they run at class-creation time. Override the name by setting
    ``__tablename__`` explicitly on the subclass.
    """

    id: str = Field(primary_key=True, max_length=ID_LENGTH)
    history_valid_from: datetime = Field(primary_key=True, sa_type=UTCDateTime)
    history_valid_to: datetime | None = Field(default=None, sa_type=UTCDateTime)
    history_changed_by_user_displayname: str = Field(max_length=NAME_LENGTH)
    history_changed_by_user_id: str = Field(max_length=NAME_LENGTH)
    history_deleted: bool = Field(default=False)

    @classmethod
    def from_entity(cls, user: User, entity: E, timestamp: datetime, *, deleted: bool = False) -> Self:
        """Open a new history row mirroring ``entity``'s columns, stamped with the actor and time.

        Copies the columns the entity and this history table share (by name); entity-only columns
        (e.g. an operational soft-delete flag) are ignored.
        """
        shared = {key: value for key, value in entity.model_dump().items() if key in cls.model_fields}
        return cls(
            **shared,
            history_valid_from=timestamp,
            history_changed_by_user_displayname=user.display_name,
            history_changed_by_user_id=user.id,
            history_deleted=deleted,
        )

    @classmethod
    def close_open_interval(cls, session: Session, entity_id: str, timestamp: datetime | None = None) -> datetime:
        """Close this entity's open interval (``history_valid_to IS NULL``), if any, at ``timestamp``.

        Returns the timestamp used, so the caller can reuse it as the new version's ``history_valid_from``
        (giving contiguous half-open intervals ``[from, to)``).
        """
        timestamp = timestamp or utc_now()
        open_row = session.exec(
            select(cls).where(
                col(cls.id) == entity_id,
                col(cls.history_valid_to).is_(None),
            )
        ).first()
        if open_row is not None:
            open_row.history_valid_to = timestamp
        return timestamp

    @classmethod
    def at_timestamp(
        cls,
        session: Session,
        entity_id: str,
        timestamp: datetime,
        *,
        include_deleted: bool = False,
    ) -> Self | None:
        """The version of ``entity_id`` valid at ``timestamp`` (half-open ``[from, to)``), or ``None``.

        Intervals never overlap, so at most one row matches. A tombstone (``history_deleted``) counts
        as "did not exist" and yields ``None`` by default; pass ``include_deleted=True`` to get the
        tombstone row itself (e.g. to show "deleted at …").
        """
        stmt = select(cls).where(
            col(cls.id) == entity_id,
            col(cls.history_valid_from) <= timestamp,
            or_(
                col(cls.history_valid_to).is_(None),
                col(cls.history_valid_to) > timestamp,
            ),
        )
        if not include_deleted:
            stmt = stmt.where(col(cls.history_deleted) == false())
        return session.exec(stmt).one_or_none()

    @classmethod
    def all_at_timestamp(
        cls,
        session: Session,
        timestamp: datetime,
        *,
        include_deleted: bool = False,
    ) -> Sequence[Self]:
        """Every entity's version valid at ``timestamp`` (half-open ``[from, to)``).

        The set-valued companion to :meth:`at_timestamp`: one row per entity that
        existed at ``timestamp`` (tombstones excluded unless ``include_deleted``).
        Backs cross-aggregate reverse lookups that must run against a historical
        snapshot rather than the live tables.
        """
        stmt = select(cls).where(
            col(cls.history_valid_from) <= timestamp,
            or_(
                col(cls.history_valid_to).is_(None),
                col(cls.history_valid_to) > timestamp,
            ),
        )
        if not include_deleted:
            stmt = stmt.where(col(cls.history_deleted) == false())
        return session.exec(stmt).all()

    @classmethod
    def record(
        cls,
        session: Session,
        user: User,
        entity: E,
        *,
        timestamp: datetime | None = None,
        deleted: bool = False,
    ) -> Self:
        """Append a new version: close the previous open interval, then add an open row mirroring ``entity``.

        The single per-entity write path — it always closes before opening, so the "at most one open
        interval per id" invariant can't be broken by forgetting a step. ``timestamp`` defaults to now;
        pass one to backdate or to align several entities to the same instant. Returns the added row.
        """
        timestamp = cls.close_open_interval(session, entity.id, timestamp)
        row = cls.from_entity(user, entity, timestamp, deleted=deleted)
        session.add(row)
        return row

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore  # declared_attr vs SQLModel's __tablename__ class var
        return _history_tablename(cls.__name__)

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Index, ...]:
        # at most one open interval (history_valid_to IS NULL) per id; name follows the resolved
        # table name, whether derived above or overridden on the subclass.
        name = cls.__tablename__
        return (
            Index(
                f"uq_{name}_open",
                "id",
                unique=True,
                sqlite_where=text("history_valid_to IS NULL"),
                mssql_where=text("history_valid_to IS NULL"),
                postgresql_where=text("history_valid_to IS NULL"),
            ),
        )
