from commons.settings import AppSettings
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from .files import Directory, DirectoryListing, File, Files


class LocalFile(File):
    """Local file system implementation of File."""

    def __init__(self, key: str, path: Path) -> None:
        self._key = key
        self._path = path

    @property
    def key(self) -> str:
        return self._key

    @property
    def size(self) -> int:
        return self._path.stat().st_size

    @property
    def last_modified(self) -> datetime:
        return datetime.fromtimestamp(self._path.stat().st_mtime, tz=UTC)

    def open(self) -> BytesIO:
        return BytesIO(self._path.read_bytes())


class LocalFiles(Files):
    """Local file system implementation of Files."""

    def __init__(self, root: Path | str | None = None) -> None:
        if root is None:
            settings = AppSettings.read()
            root = settings.data_dir / "files"

        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        """Convert a key to a file system path."""
        relative = key.lstrip("/")
        return self._root / relative

    def _path_to_key(self, path: Path) -> str:
        """Convert a file system path to a key."""
        relative = path.relative_to(self._root)
        return "/" + str(relative)

    def find(self, key: str) -> File | None:
        path = self._key_to_path(key)
        if path.is_file():
            return LocalFile(key, path)
        return None

    def list(self, path: str = "/") -> list[File]:
        normalized_path = path.rstrip("/")
        files: list[File] = []

        if not self._root.exists():
            return files

        for file_path in self._root.rglob("*"):
            if file_path.is_file():
                key = self._path_to_key(file_path)
                if key.startswith(normalized_path + "/") or (normalized_path == "" and key.startswith("/")):
                    files.append(LocalFile(key, file_path))

        return files

    def list_directory(self, path: str = "/") -> DirectoryListing:
        folder = self._key_to_path(path.rstrip("/"))
        directories: list[Directory] = []
        files: list[File] = []

        # Keys with `..` must not list folders outside the root.
        if not folder.is_dir() or not folder.resolve().is_relative_to(self._root.resolve()):
            return DirectoryListing(directories=directories, files=files)

        for entry in folder.iterdir():
            key = self._path_to_key(entry)
            if entry.is_file():
                files.append(LocalFile(key, entry))
            elif entry.is_dir() and any(p.is_file() for p in entry.rglob("*")):
                directories.append(Directory(key))

        return DirectoryListing(
            directories=sorted(directories, key=lambda d: d.key),
            files=sorted(files, key=lambda f: f.key),
        )

    def _put(self, key: str, data: BytesIO) -> None:
        path = self._key_to_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.read())

    def _delete(self, key: str, recursive: bool) -> int:
        if recursive:
            normalized_path = key.rstrip("/")
            count = 0

            for file_path in list(self._root.rglob("*")):
                if file_path.is_file():
                    file_key = self._path_to_key(file_path)
                    if file_key == key or file_key.startswith(normalized_path + "/"):
                        file_path.unlink()
                        count += 1

            self._cleanup_empty_dirs()
            return count
        else:
            path = self._key_to_path(key)
            if path.is_file():
                path.unlink()
                self._cleanup_empty_dirs()
                return 1
            return 0

    def _cleanup_empty_dirs(self) -> None:
        """Remove empty directories under root."""
        for dir_path in sorted(self._root.rglob("*"), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()
