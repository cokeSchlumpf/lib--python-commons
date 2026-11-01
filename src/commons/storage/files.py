from abc import ABC, abstractmethod
from commons import string_operators
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO


class File(ABC):
    @property
    @abstractmethod
    def key(self) -> str: ...

    @property
    def size(self) -> int:
        """
        The size of the file in bytes.

        The backends of commons know it without reading the file; this default reads the content.
        """
        return len(self.open().getvalue())

    @property
    def last_modified(self) -> datetime:
        """
        When the file was last written, with time zone (UTC).

        Every backend of commons provides it. It isn't abstract, so subclasses outside commons that don't implement
        it keep working until it is read; this default raises `NotImplementedError`.
        """
        raise NotImplementedError(f"{type(self).__name__} doesn't implement last_modified.")

    def get(self) -> BytesIO:
        return self.open()

    @abstractmethod
    def open(self) -> BytesIO: ...


@dataclass(frozen=True)
class Directory:
    """
    A virtual directory: it exists as long as at least one file is stored below it.

    The key is an absolute path without a trailing slash, e.g. `/foo/bar`.
    """

    key: str


@dataclass(frozen=True)
class DirectoryListing:
    """The directories and files directly below a path, each sorted by key."""

    directories: list[Directory]
    files: list[File]


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

    def list_directory(self, path: str = "/") -> DirectoryListing:
        """
        Get the directories and files directly below the provided path, not the ones further down.

        Directories are virtual: a directory is listed if at least one file is stored below it, at any depth.
        Only full path segments match, as in `list`. `/foo` and `/foo/` are the same path; a path with nothing
        below it (a file key or a missing key) returns an empty listing.

        With the files

        ```
        /foo/a.txt
        /foo/bar/b.txt
        /foo/bar/baz/c.txt
        /foo-bar/d.txt
        ```

        `list_directory("/foo")` returns the directory `/foo/bar` and the file `/foo/a.txt`.
        """
        base = path.rstrip("/")
        directories: set[str] = set()
        files: list[File] = []

        for file in self.list(path):
            rest = file.key.removeprefix(base + "/")
            if rest == file.key:
                continue  # not below the path

            if "/" in rest:
                directories.add(base + "/" + rest.split("/", 1)[0])
            else:
                files.append(file)

        return DirectoryListing(
            directories=[Directory(key) for key in sorted(directories)],
            files=sorted(files, key=lambda f: f.key),
        )

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
