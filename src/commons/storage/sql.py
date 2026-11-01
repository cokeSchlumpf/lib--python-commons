from commons.database_operators import create_engine
from commons.datetime_operators import utc_now
from datetime import UTC, datetime
from io import BytesIO

from sqlalchemy import DateTime, Engine, LargeBinary, String, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
    sessionmaker,
)

from .files import File, Files


class _FilePEBase(MappedAsDataclass, DeclarativeBase):
    pass


class _FilePE(_FilePEBase):
    __tablename__ = "files"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    last_modified: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=utc_now)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns datetimes without time zone; they are stored as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SQLFile(File):
    """SQL implementation of File."""

    def __init__(self, key: str, data: bytes, *, last_modified: datetime | None = None) -> None:
        self._key = key
        self._data = data
        self._last_modified = last_modified

    @property
    def key(self) -> str:
        return self._key

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def last_modified(self) -> datetime | None:
        return self._last_modified

    def open(self) -> BytesIO:
        return BytesIO(self._data)


class SQLFiles(Files):
    """
    SQL implementation of Files for storing binary files in a database table.

    The table `files` has the columns `key`, `data` and `last_modified`. A table created by a version of commons
    before 1.4 has no column `last_modified`; it isn't migrated, so drop it or add the column by hand.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        if engine is None:
            engine = create_engine()

        self._engine = engine
        _FilePE.metadata.create_all(self._engine, checkfirst=True)
        self._create_session = sessionmaker(bind=self._engine)

    def find(self, key: str) -> File | None:
        with self._create_session() as session:
            stmt = select(_FilePE).where(_FilePE.key == key)
            result = session.execute(stmt).scalar_one_or_none()

            if result:
                return SQLFile(result.key, result.data, last_modified=_as_utc(result.last_modified))
            return None

    # shortcut: list and the default list_directory load every row with its bytes, fine for the small tables
    # SQLFiles is used for; filter in SQL and load the bytes lazily when it holds many or large files.
    def list(self, path: str = "/") -> list[File]:
        normalized_path = path.rstrip("/")

        with self._create_session() as session:
            stmt = select(_FilePE)
            results = session.execute(stmt).scalars().all()

            files: list[File] = []
            for result in results:
                if result.key.startswith(normalized_path + "/") or (
                    normalized_path == "" and result.key.startswith("/")
                ):
                    files.append(SQLFile(result.key, result.data, last_modified=_as_utc(result.last_modified)))

            return files

    def _put(self, key: str, data: BytesIO) -> None:
        binary_data = data.read()

        with self._create_session() as session:
            existing = session.execute(select(_FilePE).where(_FilePE.key == key)).scalar_one_or_none()

            if existing:
                existing.data = binary_data
                existing.last_modified = utc_now()
                session.merge(existing)
            else:
                file_pe = _FilePE(key=key, data=binary_data)
                session.add(file_pe)

            session.commit()

    def _delete(self, key: str, recursive: bool) -> int:
        with self._create_session() as session:
            if recursive:
                normalized_path = key.rstrip("/")
                stmt = select(_FilePE)
                results = session.execute(stmt).scalars().all()

                count = 0
                for result in results:
                    if result.key == key or result.key.startswith(normalized_path + "/"):
                        session.delete(result)
                        count += 1

                session.commit()
                return count
            else:
                existing = session.execute(select(_FilePE).where(_FilePE.key == key)).scalar_one_or_none()

                if existing:
                    session.delete(existing)
                    session.commit()
                    return 1
                return 0
