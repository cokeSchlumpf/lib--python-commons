from commons import string_operators
from io import BytesIO

from .files import File, Files


class _PrefixedFile(File):
    """Wraps an inner File and strips the prefix from its key."""

    def __init__(self, inner: File, prefix: str) -> None:
        self._inner = inner
        self._prefix = prefix

    @property
    def key(self) -> str:
        return self._inner.key.removeprefix(self._prefix)

    def open(self) -> BytesIO:
        return self._inner.open()


class FilesWithPrefix(Files):
    """Delegate that transparently prepends a path prefix to all file operations."""

    def __init__(self, inner: Files, prefix: str) -> None:
        prefix = string_operators.normalize_path(string_operators.ensure_path_slugified(prefix))
        assert len(prefix) > 1, "The prefix must have at least two characters (e.g. '/tenant')."
        self._inner = inner
        self._prefix = prefix

    def _add_prefix(self, key: str) -> str:
        return self._prefix + key

    def _strip_prefix(self, file: File) -> File:
        return _PrefixedFile(file, self._prefix)

    def find(self, key: str) -> File | None:
        result = self._inner.find(self._add_prefix(key))
        if result is None:
            return None
        return self._strip_prefix(result)

    def list(self, path: str = "/") -> list[File]:
        results = self._inner.list(self._add_prefix(path))
        return [self._strip_prefix(f) for f in results]

    def _put(self, key: str, data: BytesIO) -> None:
        self._inner._put(self._add_prefix(key), data)

    def _delete(self, key: str, recursive: bool) -> int:
        return self._inner._delete(self._add_prefix(key), recursive)
