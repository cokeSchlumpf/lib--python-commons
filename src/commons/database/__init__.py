"""SQLModel/SQLAlchemy building blocks shared across apps.

Reusable persistence primitives that sit *below* any one app's ORM models:

- **Ids** (:func:`new_id`, from :mod:`commons.id_operators`) — time-ordered UUIDv7 strings for new rows.
- **Column length bounds** (:data:`ID_LENGTH`, :data:`CODE_LENGTH`, :data:`NAME_LENGTH`)
  — pick a bound so String columns stay indexable on SQL Server.
- **Column types** (:class:`EnumString`, :class:`PydanticJSON`, :class:`UTCDateTime`, :class:`UnicodeCode`,
  :class:`UnicodeName`) — ``TypeDecorator``s handed to ``Field(sa_type=...)``.
- **Table mixins** (:class:`EntityMixin`, :class:`HistoryMixin`) — a UUIDv7-PK operational
  entity base and its temporal history-table companion.
- **Unit-of-work ports** (:class:`UnitOfWork`, :class:`UnitOfWorkFactory`) — abstract
  transactional-scope contracts, generic over an app-defined repository bundle ``T``.
- **SQL unit of work** (:class:`SqlUnitOfWork`, :class:`SqlUnitOfWorkFactory`) — a
  ``Session``-per-scope implementation of those ports; the request actor is injected
  (``current_user_provider``) so the library stays free of any web-framework dependency.

These are engine-portable (SQLite for tests, SQL Server / Azure SQL in production); the
SQL-Server-only pieces (filtered indexes) are gated by dialect.

**Text columns on SQL Server.** SQLModel makes ``str`` columns ``VARCHAR(n)``. With the default collation of
Azure SQL (code page 1252), ``VARCHAR`` keeps German umlauts but stores other characters (``ł``, ``ş``, Cyrillic,
Greek, emoji) as ``?``, silently. Use ``VARCHAR`` (plain ``Field(max_length=...)``) for ASCII values: ids, codes,
hashes, e-mail addresses, URLs, keys. Use ``NVARCHAR`` (:class:`UnicodeCode`, :class:`UnicodeName`, or
``Unicode(n)`` in a ``Column``) for names and free text people enter. ``create_all`` doesn't change existing
tables; convert a column with e.g. ``ALTER TABLE registered_users ALTER COLUMN display_name NVARCHAR(128) NOT NULL``
(keep the column's length and nullability, and drop and recreate an index on it first).
"""

from commons.id_operators import new_id

from .column_lengths import CODE_LENGTH, ID_LENGTH, NAME_LENGTH
from .entity import EntityMixin
from .history import HistoryMixin
from .types import EnumString, PydanticJSON, UnicodeCode, UnicodeName, UTCDateTime
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
    "UnicodeCode",
    "UnicodeName",
    "UnitOfWork",
    "UnitOfWorkFactory",
    "new_id",
]
