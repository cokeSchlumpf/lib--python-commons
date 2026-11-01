from datetime import datetime
from io import BytesIO

try:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
    from azure.storage.blob import BlobPrefix, BlobProperties, BlobServiceClient, ContainerClient
except ImportError:
    # raise ImportError("Azure dependencies are missing.Install with: pip install lib-commons[azure]") from e
    pass

from commons.settings import AzureStorageSettings

from .files import Directory, DirectoryListing, File, Files


class AzureFile(File):
    """Lazy-loading Azure Blob Storage file.

    The blob bytes are not fetched until ``open()`` is called. ``size`` and ``last_modified`` come from the listing
    or lookup that created the file; if they weren't given, the blob's properties are fetched once on first access.
    """

    def __init__(
        self,
        key: str,
        container_client: ContainerClient,
        *,
        size: int | None = None,
        last_modified: datetime | None = None,
    ) -> None:
        self._key = key
        self._container_client = container_client
        self._size = size
        self._last_modified = last_modified

    @classmethod
    def _from_properties(cls, properties: BlobProperties, container_client: ContainerClient) -> "AzureFile":
        return cls(
            "/" + properties.name,
            container_client,
            size=properties.size,
            last_modified=properties.last_modified,
        )

    def _fetch_properties(self) -> None:
        if self._size is None or self._last_modified is None:
            properties = self._container_client.get_blob_client(self._key.lstrip("/")).get_blob_properties()
            self._size = properties.size
            self._last_modified = properties.last_modified

    @property
    def key(self) -> str:
        return self._key

    @property
    def size(self) -> int:
        self._fetch_properties()
        assert self._size is not None
        return self._size

    @property
    def last_modified(self) -> datetime | None:
        self._fetch_properties()
        return self._last_modified

    def open(self) -> BytesIO:
        blob = self._container_client.get_blob_client(self._key.lstrip("/"))
        return BytesIO(blob.download_blob().readall())


def _prefix(path: str) -> str:
    """The blob name prefix of everything below a path: `/foo/` and `/foo` give `foo/`, the root gives ``."""
    prefix = path.strip("/")
    return prefix + "/" if prefix else ""


def _build_container_client(settings: AzureStorageSettings) -> ContainerClient:
    if settings.auth_mode == "connection_string":
        service = BlobServiceClient.from_connection_string(settings.connection_string)
    elif settings.auth_mode == "account_key":
        account_url = settings.account_url or f"https://{settings.account_name}.blob.core.windows.net"
        service = BlobServiceClient(
            account_url=account_url,
            credential={"account_name": settings.account_name, "account_key": settings.account_key},
        )
    else:  # default_credential
        service = BlobServiceClient(account_url=settings.account_url, credential=DefaultAzureCredential())
    return service.get_container_client(settings.container)


class AzureFiles(Files):
    """Azure Blob Storage implementation of Files.

    Maps each ``Files`` key (e.g. ``/foo/bar.txt``) to a blob name in a single
    Azure Storage container (e.g. ``foo/bar.txt``). Multi-tenant prefixing is
    handled by :class:`commons.storage.FilesWithPrefix`.
    """

    def __init__(
        self,
        settings: AzureStorageSettings | None = None,
        *,
        container_client: ContainerClient | None = None,
    ) -> None:
        if container_client is not None:
            self._container_client = container_client
            return

        if settings is None:
            settings = AzureStorageSettings.read()

        assert settings.container, "AzureStorageSettings.container must be set."
        self._container_client = _build_container_client(settings)

    def find(self, key: str) -> File | None:
        blob = self._container_client.get_blob_client(key.lstrip("/"))
        try:
            properties = blob.get_blob_properties()
        except ResourceNotFoundError:
            return None
        return AzureFile(key, self._container_client, size=properties.size, last_modified=properties.last_modified)

    def list(self, path: str = "/") -> list[File]:
        blobs = self._container_client.list_blobs(name_starts_with=_prefix(path))
        return [AzureFile._from_properties(b, self._container_client) for b in blobs]

    def list_directory(self, path: str = "/") -> DirectoryListing:
        directories: list[Directory] = []
        files: list[File] = []

        # One level only: with a delimiter, the service returns the blobs below deeper paths as one prefix each.
        for item in self._container_client.walk_blobs(name_starts_with=_prefix(path), delimiter="/"):
            if isinstance(item, BlobPrefix):
                directories.append(Directory("/" + item.name.rstrip("/")))
            else:
                files.append(AzureFile._from_properties(item, self._container_client))

        return DirectoryListing(
            directories=sorted(directories, key=lambda d: d.key),
            files=sorted(files, key=lambda f: f.key),
        )

    def _put(self, key: str, data: BytesIO) -> None:
        blob = self._container_client.get_blob_client(key.lstrip("/"))
        data.seek(0)  # if data is already partially read
        blob.upload_blob(data.read(), overwrite=True)

    def _delete(self, key: str, recursive: bool) -> int:
        if recursive:
            prefix = key.rstrip("/").lstrip("/")
            count = 0
            for blob in self._container_client.list_blobs(name_starts_with=prefix + "/"):
                self._container_client.delete_blob(blob.name)
                count += 1
            try:
                self._container_client.delete_blob(prefix)
                count += 1
            except ResourceNotFoundError:
                pass
            return count

        try:
            self._container_client.delete_blob(key.lstrip("/"))
            return 1
        except ResourceNotFoundError:
            return 0
