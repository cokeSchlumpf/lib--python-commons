"""Directory listings and file metadata, the same cases for every backend of `Files`."""

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobPrefix, BlobProperties
from sqlalchemy import create_engine

from commons.storage import (
    AzureFiles,
    Directory,
    DirectoryListing,
    File,
    Files,
    FilesWithPrefix,
    LocalFiles,
    SQLFiles,
)


class _MemoryFile(File):
    """A `File` that implements only the abstract methods."""

    def __init__(self, key: str, data: bytes) -> None:
        self._key = key
        self._data = data

    @property
    def key(self) -> str:
        return self._key

    def open(self) -> BytesIO:
        return BytesIO(self._data)


class _MemoryFiles(Files):
    """A `Files` that implements only the abstract methods (and `_put`), as a subclass outside commons would."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def find(self, key: str) -> File | None:
        return _MemoryFile(key, self._data[key]) if key in self._data else None

    def list(self, path: str = "/") -> list[File]:
        base = path.rstrip("/")
        return [_MemoryFile(k, v) for k, v in self._data.items() if k.startswith(base + "/")]

    def _put(self, key: str, data: BytesIO) -> None:
        self._data[key] = data.read()

    def _delete(self, key: str, recursive: bool) -> int:
        return 1 if self._data.pop(key, None) is not None else 0


class _FakeBlobClient:
    def __init__(self, container: "_FakeContainerClient", name: str) -> None:
        self._container = container
        self._name = name

    def upload_blob(self, data: bytes, overwrite: bool = False) -> None:
        properties = BlobProperties()
        properties.name = self._name
        properties.size = len(data)
        properties.last_modified = datetime.now(UTC)
        self._container.blobs[self._name] = (properties, data)

    def get_blob_properties(self) -> BlobProperties:
        if self._name not in self._container.blobs:
            raise ResourceNotFoundError("not found")
        return self._container.blobs[self._name][0]

    def download_blob(self) -> "_FakeDownload":
        if self._name not in self._container.blobs:
            raise ResourceNotFoundError("not found")
        return _FakeDownload(self._container.blobs[self._name][1])


class _FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeContainerClient:
    """In-memory container with the documented semantics of `list_blobs` and `walk_blobs` (results in name order)."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[BlobProperties, bytes]] = {}
        self.calls: list[str] = []

    def get_blob_client(self, name: str) -> _FakeBlobClient:
        return _FakeBlobClient(self, name)

    def list_blobs(self, name_starts_with: str | None = None) -> list[BlobProperties]:
        self.calls.append("list_blobs")
        prefix = name_starts_with or ""
        return [p for name, (p, _) in sorted(self.blobs.items()) if name.startswith(prefix)]

    def walk_blobs(self, name_starts_with: str | None = None, delimiter: str = "/") -> list[BlobProperties | BlobPrefix]:
        self.calls.append("walk_blobs")
        prefix = name_starts_with or ""
        items: list[BlobProperties | BlobPrefix] = []
        prefixes: set[str] = set()
        for name, (properties, _) in sorted(self.blobs.items()):
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            if delimiter in rest:
                prefixes.add(prefix + rest.split(delimiter, 1)[0] + delimiter)
            else:
                items.append(properties)
        return [*items, *(BlobPrefix(prefix=p) for p in sorted(prefixes))]

    def delete_blob(self, name: str) -> None:
        if self.blobs.pop(name, None) is None:
            raise ResourceNotFoundError("not found")


FilesFactory = Callable[[Path], Files]

# The backends of commons; each must know the metadata of its files.
BACKENDS: dict[str, FilesFactory] = {
    "local": lambda tmp_path: LocalFiles(tmp_path / "files"),
    "sql": lambda tmp_path: SQLFiles(create_engine(f"sqlite:///{tmp_path / 'files.db'}")),
    "azure": lambda tmp_path: AzureFiles(container_client=_FakeContainerClient()),  # type: ignore[arg-type]
    "prefix": lambda tmp_path: FilesWithPrefix(LocalFiles(tmp_path / "files"), "/tenant"),
}


@pytest.fixture(params=["memory", *BACKENDS])
def files(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Files]:
    """Every backend, and a minimal subclass outside commons."""
    yield _MemoryFiles() if request.param == "memory" else BACKENDS[request.param](tmp_path)


@pytest.fixture(params=list(BACKENDS))
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Files]:
    """Every backend of commons."""
    yield BACKENDS[request.param](tmp_path)


def _put(files: Files, *keys: str) -> None:
    for key in keys:
        files.put(key, BytesIO(f"content of {key}".encode()))


def _keys(listing: DirectoryListing) -> tuple[list[str], list[str]]:
    return [d.key for d in listing.directories], [f.key for f in listing.files]


class TestListDirectory:
    def test_lists_one_level(self, files: Files) -> None:
        _put(files, "/foo/a.txt", "/foo/bar/b.txt", "/foo/bar/baz/c.txt", "/foo-bar/d.txt", "/e.txt")

        assert _keys(files.list_directory("/foo")) == (["/foo/bar"], ["/foo/a.txt"])

    def test_lists_root(self, files: Files) -> None:
        _put(files, "/foo/a.txt", "/foo-bar/d.txt", "/e.txt")

        assert _keys(files.list_directory("/")) == (["/foo", "/foo-bar"], ["/e.txt"])
        assert _keys(files.list_directory("")) == (["/foo", "/foo-bar"], ["/e.txt"])
        assert _keys(files.list_directory()) == (["/foo", "/foo-bar"], ["/e.txt"])

    def test_sorts_directories_and_files_by_key(self, files: Files) -> None:
        _put(files, "/x/c.txt", "/x/a.txt", "/x/b.txt", "/x/z/1.txt", "/x/m/1.txt", "/x/k/1.txt")

        assert _keys(files.list_directory("/x")) == (
            ["/x/k", "/x/m", "/x/z"],
            ["/x/a.txt", "/x/b.txt", "/x/c.txt"],
        )

    def test_lists_a_directory_once_for_many_files_below_it(self, files: Files) -> None:
        _put(files, "/x/sub/a.txt", "/x/sub/b.txt", "/x/sub/deep/c.txt")

        assert _keys(files.list_directory("/x")) == (["/x/sub"], [])

    def test_trailing_slash_is_the_same_path(self, files: Files) -> None:
        _put(files, "/foo/a.txt", "/foo/bar/b.txt")

        assert _keys(files.list_directory("/foo/")) == _keys(files.list_directory("/foo"))

    def test_matches_whole_segments_only(self, files: Files) -> None:
        _put(files, "/foo-bar/d.txt", "/foobar.txt")

        assert _keys(files.list_directory("/foo")) == ([], [])

    def test_file_key_returns_empty_listing(self, files: Files) -> None:
        _put(files, "/foo/a.txt")

        assert files.list_directory("/foo/a.txt") == DirectoryListing(directories=[], files=[])

    def test_missing_key_returns_empty_listing(self, files: Files) -> None:
        assert _keys(files.list_directory("/missing")) == ([], [])

    def test_empty_storage_returns_empty_listing(self, files: Files) -> None:
        assert _keys(files.list_directory("/")) == ([], [])

    def test_directory_disappears_with_its_last_file(self, files: Files) -> None:
        _put(files, "/x/sub/a.txt", "/x/b.txt")
        files.delete("/x/sub/a.txt")

        assert _keys(files.list_directory("/x")) == ([], ["/x/b.txt"])

    def test_listed_files_can_be_opened(self, files: Files) -> None:
        _put(files, "/x/a.txt")

        (file,) = files.list_directory("/x").files
        assert file.open().read() == b"content of /x/a.txt"

    def test_directories_are_values(self) -> None:
        assert Directory("/foo") == Directory("/foo")


class TestDefaultMetadata:
    """A `File` subclass outside commons keeps working with the new properties."""

    def test_size_is_the_length_of_the_content(self) -> None:
        assert _MemoryFile("/a.txt", b"12345").size == 5

    def test_last_modified_is_unknown(self) -> None:
        assert _MemoryFile("/a.txt", b"12345").last_modified is None


class TestBackendMetadata:
    def _listed(self, files: Files, key: str) -> list[File]:
        """The file as returned by `find`, `get`, `list` and `list_directory`."""
        found = files.find(key)
        assert found is not None
        directory = key.rsplit("/", 1)[0]
        return [
            found,
            files.get(key),
            *[f for f in files.list(directory) if f.key == key],
            *[f for f in files.list_directory(directory).files if f.key == key],
        ]

    def test_size_and_last_modified_are_known(self, backend: Files) -> None:
        before = datetime.now(UTC) - timedelta(seconds=2)
        backend.put("/x/a.txt", BytesIO(b"12345"))
        after = datetime.now(UTC) + timedelta(seconds=2)

        listed = self._listed(backend, "/x/a.txt")
        assert len(listed) == 4
        for file in listed:
            assert file.size == 5
            assert file.last_modified is not None
            assert file.last_modified.tzinfo is not None
            assert before <= file.last_modified <= after

    def test_metadata_does_not_open_the_file(self, backend: Files, monkeypatch: pytest.MonkeyPatch) -> None:
        backend.put("/x/a.txt", BytesIO(b"12345"))
        listed = self._listed(backend, "/x/a.txt")

        def fail(self: File) -> BytesIO:
            raise AssertionError("open() must not be called")

        for file in listed:
            monkeypatch.setattr(type(file), "open", fail)
            assert file.size == 5
            assert file.last_modified is not None

    def test_overwrite_changes_last_modified(self, backend: Files) -> None:
        backend.put("/x/a.txt", BytesIO(b"first"))
        first = backend.get("/x/a.txt").last_modified
        time.sleep(0.01)
        backend.put("/x/a.txt", BytesIO(b"second, longer"))
        second = backend.get("/x/a.txt")

        assert first is not None and second.last_modified is not None
        assert second.last_modified > first
        assert second.size == len(b"second, longer")


class TestLocalFiles:
    def test_empty_folder_is_not_listed(self, tmp_path: Path) -> None:
        files = LocalFiles(tmp_path)
        files.put("/x/a.txt", BytesIO(b"a"))
        (tmp_path / "x" / "empty" / "deeper").mkdir(parents=True)

        assert _keys(files.list_directory("/x")) == ([], ["/x/a.txt"])

    def test_does_not_list_outside_the_root(self, tmp_path: Path) -> None:
        (tmp_path / "outside.txt").write_bytes(b"secret")
        files = LocalFiles(tmp_path / "root")
        files.put("/a.txt", BytesIO(b"a"))

        assert _keys(files.list_directory("/..")) == ([], [])
        assert _keys(files.list_directory("/../root/..")) == ([], [])


class TestAzureFiles:
    def test_lists_one_level_with_one_walk_blobs_call(self) -> None:
        container = _FakeContainerClient()
        files = AzureFiles(container_client=container)  # type: ignore[arg-type]
        _put(files, "/foo/a.txt", "/foo/bar/b.txt", "/foo/bar/baz/c.txt")
        container.calls.clear()

        assert _keys(files.list_directory("/foo")) == (["/foo/bar"], ["/foo/a.txt"])
        assert container.calls == ["walk_blobs"]

    def test_metadata_from_the_listing_needs_no_further_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        container = _FakeContainerClient()
        files = AzureFiles(container_client=container)  # type: ignore[arg-type]
        _put(files, "/x/a.txt")
        (file,) = files.list_directory("/x").files

        def fail(self: _FakeBlobClient) -> None:
            raise AssertionError("no request expected")

        monkeypatch.setattr(_FakeBlobClient, "get_blob_properties", fail)
        monkeypatch.setattr(_FakeBlobClient, "download_blob", fail)
        assert file.size == len(b"content of /x/a.txt")
        assert file.last_modified is not None


class TestFilesWithPrefix:
    def test_keys_have_no_prefix_and_other_tenants_are_not_listed(self, tmp_path: Path) -> None:
        inner = LocalFiles(tmp_path)
        _put(inner, "/other/x/a.txt")
        files = FilesWithPrefix(inner, "/tenant")
        _put(files, "/x/a.txt", "/x/sub/b.txt")

        assert _keys(files.list_directory("/")) == (["/x"], [])
        assert _keys(files.list_directory("/x")) == (["/x/sub"], ["/x/a.txt"])
