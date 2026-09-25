"""SQLModel/SQLAlchemy building blocks shared across apps.

Reusable persistence primitives that sit *below* any one app's ORM models:

- **Column length bounds** (:data:`ID_LENGTH`, :data:`CODE_LENGTH`, :data:`NAME_LENGTH`)
  — pick a bound so String columns stay indexable on SQL Server.
- **Column types** (:class:`EnumString`, :class:`PydanticJSON`, :class:`UTCDateTime`)
  — ``TypeDecorator``s handed to ``Field(sa_type=...)``.
- **Table mixins** (:class:`EntityMixin`, :class:`HistoryMixin`) — a uuid-PK operational
  entity base and its temporal history-table companion.
- **Unit-of-work ports** (:class:`UnitOfWork`, :class:`UnitOfWorkFactory`) — abstract
  transactional-scope contracts, generic over an app-defined repository bundle ``T``.
- **SQL unit of work** (:class:`SqlUnitOfWork`, :class:`SqlUnitOfWorkFactory`) — a
  ``Session``-per-scope implementation of those ports; the request actor is injected
  (``current_user_provider``) so the library stays free of any web-framework dependency.

These are engine-portable (SQLite for tests, SQL Server / Azure SQL in production); the
SQL-Server-only pieces (filtered indexes) are gated by dialect.
"""

from .column_lengths import CODE_LENGTH, ID_LENGTH, NAME_LENGTH
from .entity import EntityMixin
from .history import HistoryMixin
from .types import EnumString, PydanticJSON, UTCDateTime
from .unit_of_work import CommitFunction, UnitOfWork, UnitOfWorkFactory
from .unit_of_work_sql import SqlUnitOfWork, SqlUnitOfWorkFactory


__all__ = [
    "CODE_LENGTH",
    "ID_LENGTH",
    "NAME_LENGTH",
    "CommitFunction",
    "EntityMixin",
    "EnumString",
    "HistoryMixin",
    "PydanticJSON",
    "SqlUnitOfWork",
    "SqlUnitOfWorkFactory",
    "UTCDateTime",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
