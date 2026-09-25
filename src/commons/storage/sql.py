from commons.database_operators import create_engine
from io import BytesIO

from sqlalchemy import Engine, LargeBinary, String, select
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


class SQLFile(File):
    """SQL implementation of File."""

    def __init__(self, key: str, data: bytes) -> None:
        self._key = key
        self._data = data

    @property
    def key(self) -> str:
        return self._key

    def open(self) -> BytesIO:
        return BytesIO(self._data)


class SQLFiles(Files):
    """SQL implementation of Files for storing binary files in a database table."""

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
                return SQLFile(result.key, result.data)
            return None

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
                    files.append(SQLFile(result.key, result.data))

            return files

    def _put(self, key: str, data: BytesIO) -> None:
        binary_data = data.read()

        with self._create_session() as session:
            existing = session.execute(select(_FilePE).where(_FilePE.key == key)).scalar_one_or_none()

            if existing:
                existing.data = binary_data
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
