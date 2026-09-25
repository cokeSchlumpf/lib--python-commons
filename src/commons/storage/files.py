from abc import ABC, abstractmethod
from commons import string_operators
from io import BytesIO


class File(ABC):
    @property
    @abstractmethod
    def key(self) -> str: ...

    def get(self) -> BytesIO:
        return self.open()

    @abstractmethod
    def open(self) -> BytesIO: ...


class Files(ABC):
    @abstractmethod
    def find(self, key: str) -> File | None:
        """Search a file by its key. Returns None if file doesn't exist."""
        ...

    def get(self, key: str) -> File:
        """Get a file by its key. Throws error if file does not exist."""
        file = self.find(key)
        assert file is not None, f"No file with key `{key}`"
        return file

    @abstractmethod
    def list(self, path: str = "/") -> list[File]:
        """
        Get all lists which are below provided path.

        Only full path segments match, e.g. we have the following files

        ```
        /foo/a.txt
        /foo/b.txt
        /foo-bar/c.txt
        ```

        `list("/foo")` returns

        ```
        /foo/a.txt
        /foo/b.txt
        ```
        """

    def put(self, key: str, data: BytesIO) -> None:
        """Adds or overwrites a file."""

        key_clean = string_operators.normalize_path(string_operators.ensure_path_slugified(key))
        assert key_clean == key, f"The provided key (`{key}`) is not valid. A valid key would be `{key_clean}`."
        assert len(key) > 1, "The provided key is not valid. Keys must have at least a length of two characters."

        self._put(key, data)

    def _put(self, key: str, data: BytesIO) -> None:
        """
        Adds or overwrites a file.

        The key is a validated slugified absolute path (starting with "/").
        """
        ...

    def delete(self, key: str, recursive: bool = False) -> int:
        """
        Delete a file or files by key.

        Args:
            key: The file key or path prefix to delete.
            recursive: If True, deletes all files under the given path prefix.
                       If False, only deletes the exact file matching the key.

        Returns:
            The number of files deleted.
        """
        return self._delete(key, recursive)

    @abstractmethod
    def _delete(self, key: str, recursive: bool) -> int:
        """
        Internal delete implementation.

        Returns the number of files deleted.
        """
        ...
