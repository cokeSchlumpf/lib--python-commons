from io import BytesIO

try:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
    from azure.storage.blob import BlobServiceClient, ContainerClient
except ImportError:
    # raise ImportError("Azure dependencies are missing.Install with: pip install lib-commons[azure]") from e
    pass

from commons.settings import AzureStorageSettings

from .files import File, Files


class AzureFile(File):
    """Lazy-loading Azure Blob Storage file.

    The blob bytes are not fetched until ``open()`` is called.
    """

    def __init__(self, key: str, container_client: ContainerClient) -> None:
        self._key = key
        self._container_client = container_client

    @property
    def key(self) -> str:
        return self._key

    def open(self) -> BytesIO:
        blob = self._container_client.get_blob_client(self._key.lstrip("/"))
        return BytesIO(blob.download_blob().readall())


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
            blob.get_blob_properties()
        except ResourceNotFoundError:
            return None
        return AzureFile(key, self._container_client)

    def list(self, path: str = "/") -> list[File]:
        prefix = path.lstrip("/").rstrip("/")
        prefix = prefix + "/" if prefix else ""
        blobs = self._container_client.list_blobs(name_starts_with=prefix)
        return [AzureFile("/" + b.name, self._container_client) for b in blobs]

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
