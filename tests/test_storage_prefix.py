from io import BytesIO
from pathlib import Path

import pytest

from commons.storage import FilesWithPrefix, LocalFiles


@pytest.fixture
def prefixed_files(tmp_path: Path) -> FilesWithPrefix:
    inner = LocalFiles(root=tmp_path)
    return FilesWithPrefix(inner, "/tenant")


class TestFind:
    def test_find_existing_file(self, prefixed_files: FilesWithPrefix, tmp_path: Path) -> None:
        # Write a file directly via the inner store
        inner = LocalFiles(root=tmp_path)
        inner.put("/tenant/docs/a.txt", BytesIO(b"hello"))

        result = prefixed_files.find("/docs/a.txt")
        assert result is not None
        assert result.key == "/docs/a.txt"

    def test_find_nonexistent_file(self, prefixed_files: FilesWithPrefix) -> None:
        result = prefixed_files.find("/docs/missing.txt")
        assert result is None


class TestList:
    def test_list_files(self, prefixed_files: FilesWithPrefix, tmp_path: Path) -> None:
        inner = LocalFiles(root=tmp_path)
        inner.put("/tenant/docs/a.txt", BytesIO(b"aaa"))
        inner.put("/tenant/docs/b.txt", BytesIO(b"bbb"))
        inner.put("/other/c.txt", BytesIO(b"ccc"))

        results = prefixed_files.list("/docs")
        keys = sorted(f.key for f in results)
        assert keys == ["/docs/a.txt", "/docs/b.txt"]

    def test_list_all(self, prefixed_files: FilesWithPrefix, tmp_path: Path) -> None:
        inner = LocalFiles(root=tmp_path)
        inner.put("/tenant/a.txt", BytesIO(b"aaa"))
        inner.put("/tenant/sub/b.txt", BytesIO(b"bbb"))

        results = prefixed_files.list("/")
        keys = sorted(f.key for f in results)
        assert keys == ["/a.txt", "/sub/b.txt"]


class TestPutAndGet:
    def test_round_trip(self, prefixed_files: FilesWithPrefix) -> None:
        prefixed_files.put("/docs/hello.txt", BytesIO(b"world"))

        result = prefixed_files.find("/docs/hello.txt")
        assert result is not None
        assert result.key == "/docs/hello.txt"
        assert result.open().read() == b"world"

    def test_stored_with_prefix(self, prefixed_files: FilesWithPrefix, tmp_path: Path) -> None:
        prefixed_files.put("/docs/hello.txt", BytesIO(b"world"))

        # Verify the inner store has the prefixed key
        inner = LocalFiles(root=tmp_path)
        result = inner.find("/tenant/docs/hello.txt")
        assert result is not None
        assert result.open().read() == b"world"


class TestDelete:
    def test_delete_single(self, prefixed_files: FilesWithPrefix) -> None:
        prefixed_files.put("/docs/a.txt", BytesIO(b"aaa"))

        count = prefixed_files.delete("/docs/a.txt")
        assert count == 1
        assert prefixed_files.find("/docs/a.txt") is None

    def test_delete_recursive(self, prefixed_files: FilesWithPrefix) -> None:
        prefixed_files.put("/docs/a.txt", BytesIO(b"aaa"))
        prefixed_files.put("/docs/sub/b.txt", BytesIO(b"bbb"))
        prefixed_files.put("/other/c.txt", BytesIO(b"ccc"))

        count = prefixed_files.delete("/docs", recursive=True)
        assert count == 2
        assert prefixed_files.find("/docs/a.txt") is None
        assert prefixed_files.find("/docs/sub/b.txt") is None
        assert prefixed_files.find("/other/c.txt") is not None


class TestPrefixNormalization:
    def test_prefix_is_normalized(self, tmp_path: Path) -> None:
        inner = LocalFiles(root=tmp_path)
        fp = FilesWithPrefix(inner, "//My Tenant//")
        # Should be normalized to "/my-tenant"
        assert fp._prefix == "/my-tenant"

    def test_prefix_must_be_longer_than_one(self, tmp_path: Path) -> None:
        inner = LocalFiles(root=tmp_path)
        with pytest.raises(AssertionError):
            FilesWithPrefix(inner, "/")
