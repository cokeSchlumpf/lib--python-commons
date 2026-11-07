"""A fake Azure Storage container with the behaviour of append blobs that `AzureBlobEventLog` depends on."""

from types import SimpleNamespace

from azure.core.exceptions import HttpResponseError, ResourceExistsError, ResourceNotFoundError


def _sealed() -> HttpResponseError:
    error = HttpResponseError(message="The blob is sealed.")
    error.error_code = "BlobIsSealed"
    return error


class FakeBlob:
    def __init__(self, container: "FakeContainer", name: str) -> None:
        self.container = container
        self.name = name

    def _stored(self) -> SimpleNamespace:
        stored = self.container.blobs.get(self.name)
        if stored is None:
            raise ResourceNotFoundError(message=self.name)
        return stored

    def create_append_blob(self, match_condition: object = None) -> None:
        assert match_condition is not None, "Without a condition, this replaces an existing blob."
        if self.name in self.container.blobs:
            raise ResourceExistsError(message=self.name)
        self.container.blobs[self.name] = SimpleNamespace(data=b"", blocks=0, sealed=False)

    def append_block(self, data: bytes) -> dict:
        stored = self._stored()
        if stored.sealed:
            raise _sealed()
        stored.data += data
        stored.blocks += 1
        return {"blob_committed_block_count": stored.blocks}

    def seal_append_blob(self) -> None:
        self._stored().sealed = True

    def get_blob_properties(self) -> SimpleNamespace:
        stored = self._stored()
        return SimpleNamespace(size=len(stored.data), is_append_blob_sealed=stored.sealed)

    def download_blob(self, offset: int = 0, length: int | None = None) -> SimpleNamespace:
        data = self._stored().data
        end = len(data) if length is None else offset + length
        return SimpleNamespace(readall=lambda: data[offset:end])

    def upload_blob(self, data: bytes, overwrite: bool = False) -> None:
        assert overwrite
        self.container.blobs[self.name] = SimpleNamespace(data=data, blocks=1, sealed=False)


class FakeContainer:
    def __init__(self) -> None:
        self.blobs: dict[str, SimpleNamespace] = {}
        self.created = 0

    def create_container(self) -> None:
        self.created += 1
        if self.created > 1:
            raise ResourceExistsError(message="container")

    def get_blob_client(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def list_blobs(self, name_starts_with: str = "") -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in sorted(self.blobs) if name.startswith(name_starts_with)]
