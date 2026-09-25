"""SQLModel-compatible column types (``TypeDecorator`` subclasses).

Handed to SQLModel's ``Field(sa_type=...)`` as *types* (not instances), so SQLModel
instantiates them into concrete columns. Kept together because they share that one
role — turning a Python value into a portable, length-bounded, or self-validating
database column.
"""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import TypeAdapter
from sqlalchemy import JSON, DateTime, Dialect, String, TypeDecorator

from .column_lengths import ENUM_LENGTH

T = TypeVar("T")


class EnumString(TypeDecorator[str]):
    """A length-bounded ``String`` for Literal-valued columns (status / kind / mode / license).

    A ``TypeDecorator`` rather than ``String(ENUM_LENGTH)`` so it can be handed to
    SQLModel's ``sa_type`` as a *type* (which SQLModel instantiates into a
    ``VARCHAR(ENUM_LENGTH)`` column) instead of an instance — SQLModel types ``sa_type``
    as ``type[Any]``, so passing an instance fails type checking.
    """

    impl = String(ENUM_LENGTH)
    cache_ok = True


class PydanticJSON(TypeDecorator[T], Generic[T]):
    """JSON column that round-trips any Pydantic-validatable type ``T`` via a ``TypeAdapter``.

    ``T`` can be a model, ``list[Model]``, ``dict[str, Model]``, etc. Writes dump to
    JSON-native values (so the JSON impl can encode them); reads rebuild validated
    instances rather than handing back raw dicts.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, data_type: type[T], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Stored under the ``__init__`` arg name so SQLAlchemy's cache key picks it up.
        self.data_type = data_type
        self._adapter: TypeAdapter[T] = TypeAdapter(data_type)

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        # ``validate_python`` first so we serialise canonically whether handed model
        # instances (the normal ORM path) or raw dicts (e.g. a history mixin that
        # snapshots rows via ``model_dump``); table models skip validation on init,
        # so dicts would otherwise reach here and trip ``dump_python``'s warnings.
        return self._adapter.dump_python(self._adapter.validate_python(value), mode="json")

    def process_result_value(self, value: Any, dialect: Dialect) -> T | None:
        if value is None:
            return None
        return self._adapter.validate_python(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Store tz-aware datetimes as naive UTC (engine-portable). Read back naive (repo convention)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
