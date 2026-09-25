from io import BytesIO
import pytest
from azure.core.exceptions import ResourceNotFoundError
from unittest.mock import MagicMock
from unittest.mock import patch

from commons.settings import AzureStorageSettings
from commons.storage import azure as azure_module
from commons.storage.azure import AzureFiles
from commons.storage.azure import AzureFile


class TestAzureFile:
    def test_key_returned_as_is(self):
        container_client = MagicMock()
        f = AzureFile("/foo/bar.txt", container_client)
        assert f.key == "/foo/bar.txt"

    def test_open_strips_leading_slash_and_downloads(self):
        container_client = MagicMock()
        blob_client = container_client.get_blob_client.return_value
        blob_client.download_blob.return_value.readall.return_value = b"hello world"

        f = AzureFile("/foo/bar.txt", container_client)
        result = f.open()

        container_client.get_blob_client.assert_called_once_with("foo/bar.txt")
        assert isinstance(result, BytesIO)
        assert result.read() == b"hello world"


@pytest.fixture
def container_client() -> MagicMock:
    return MagicMock()

@pytest.fixture
def azure_files(container_client: MagicMock) -> AzureFiles:
    return AzureFiles(container_client=container_client)


class TestAzureFilesFind:
    def test_returns_file_when_blob_exists(self, azure_files: AzureFiles, container_client: MagicMock):
        # get_blob_properties returns silently when the blob exists.
        container_client.get_blob_client.return_value.get_blob_properties.return_value = MagicMock()

        result = azure_files.find("/foo/bar.txt")

        container_client.get_blob_client.assert_called_with("foo/bar.txt")
        assert result is not None
        assert result.key == "/foo/bar.txt"

    def test_returns_none_when_blob_missing(self, azure_files: AzureFiles, container_client: MagicMock):
        container_client.get_blob_client.return_value.get_blob_properties.side_effect = ResourceNotFoundError(
            "not found"
        )

        result = azure_files.find("/foo/missing.txt")
        assert result is None


class TestAzureFilesList:
    def test_list_root_passes_empty_prefix(self, azure_files: AzureFiles, container_client: MagicMock):
        blob_a = MagicMock()
        blob_a.name = "foo/a.txt"
        blob_b = MagicMock()
        blob_b.name = "bar/b.txt"
        container_client.list_blobs.return_value = [blob_a, blob_b]

        results = azure_files.list("/")

        container_client.list_blobs.assert_called_once_with(name_starts_with="")
        keys = sorted(f.key for f in results)
        assert keys == ["/bar/b.txt", "/foo/a.txt"]

    def test_list_with_path_pushes_prefix(self, azure_files: AzureFiles, container_client: MagicMock):
        blob_a = MagicMock()
        blob_a.name = "foo/a.txt"
        blob_b = MagicMock()
        blob_b.name = "foo/sub/b.txt"
        container_client.list_blobs.return_value = [blob_a, blob_b]

        results = azure_files.list("/foo")

        container_client.list_blobs.assert_called_once_with(name_starts_with="foo/")
        keys = sorted(f.key for f in results)
        assert keys == ["/foo/a.txt", "/foo/sub/b.txt"]

    def test_list_returns_empty_when_no_blobs(self, azure_files: AzureFiles, container_client: MagicMock):
        container_client.list_blobs.return_value = []
        results = azure_files.list("/foo")
        assert results == []

    def test_list_strips_trailing_slash_from_path(self, azure_files: AzureFiles, container_client: MagicMock):
        container_client.list_blobs.return_value = []
        azure_files.list("/foo/")
        container_client.list_blobs.assert_called_once_with(name_starts_with="foo/")


class TestAzureFilesPut:
    def test_put_uploads_with_overwrite(self, azure_files: AzureFiles, container_client: MagicMock):
        # Use the public put() so we also exercise the protocol's key validation.
        azure_files.put("/foo/bar.txt", BytesIO(b"hello"))

        container_client.get_blob_client.assert_called_with("foo/bar.txt")
        container_client.get_blob_client.return_value.upload_blob.assert_called_once_with(b"hello", overwrite=True)

    def test_put_rejects_invalid_key(self, azure_files: AzureFiles):
        with pytest.raises(AssertionError):
            azure_files.put("/Foo Bar/Baz.txt", BytesIO(b"x"))  # Not slugified


class TestAzureFilesDeleteSingle:
    def test_delete_existing_returns_one(self, azure_files: AzureFiles, container_client: MagicMock):
        result = azure_files.delete("/foo/bar.txt")

        container_client.delete_blob.assert_called_once_with("foo/bar.txt")
        assert result == 1

    def test_delete_missing_returns_zero(self, azure_files: AzureFiles, container_client: MagicMock):
        container_client.delete_blob.side_effect = ResourceNotFoundError("missing")

        result = azure_files.delete("/foo/missing.txt")

        assert result == 0


class TestAzureFilesDeleteRecursive:
    def test_recursive_deletes_all_under_prefix_and_exact_match(
        self, azure_files: AzureFiles, container_client: MagicMock
    ):
        # list_blobs is called with the prefix sweep; delete_blob is then called for each.
        b1 = MagicMock()
        b1.name = "foo/a.txt"
        b2 = MagicMock()
        b2.name = "foo/sub/b.txt"
        container_client.list_blobs.return_value = [b1, b2]
        # Exact-match delete for "foo" succeeds (treated as a sentinel blob).
        container_client.delete_blob.side_effect = None

        result = azure_files.delete("/foo", recursive=True)

        container_client.list_blobs.assert_called_once_with(name_starts_with="foo/")
        # 2 from sweep + 1 from exact match.
        assert container_client.delete_blob.call_count == 3
        delete_targets = [c.args[0] for c in container_client.delete_blob.call_args_list]
        assert "foo/a.txt" in delete_targets
        assert "foo/sub/b.txt" in delete_targets
        assert "foo" in delete_targets
        assert result == 3

    def test_recursive_swallows_missing_exact_match(
        self, azure_files: AzureFiles, container_client: MagicMock
    ):
        b1 = MagicMock()
        b1.name = "foo/a.txt"
        container_client.list_blobs.return_value = [b1]

        # First call (sweep) succeeds; second call (exact-match) raises.
        container_client.delete_blob.side_effect = [None, ResourceNotFoundError("missing")]

        result = azure_files.delete("/foo", recursive=True)

        assert result == 1  # Only the swept blob counts.

    def test_recursive_returns_zero_when_nothing_matches(
        self, azure_files: AzureFiles, container_client: MagicMock
    ):
        container_client.list_blobs.return_value = []
        container_client.delete_blob.side_effect = ResourceNotFoundError("missing")

        result = azure_files.delete("/foo", recursive=True)

        assert result == 0



class TestBuildContainerClient:
    def test_connection_string_mode(self):
        settings = AzureStorageSettings(
            auth_mode="connection_string",
            container="files",
            connection_string="DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=k;EndpointSuffix=core.windows.net",
        )

        with patch.object(azure_module, "BlobServiceClient") as fake_service_cls:
            azure_module._build_container_client(settings)

        fake_service_cls.from_connection_string.assert_called_once_with(
            "DefaultEndpointsProtocol=https;AccountName=acct;AccountKey=k;EndpointSuffix=core.windows.net"
        )
        fake_service_cls.from_connection_string.return_value.get_container_client.assert_called_once_with("files")

    def test_account_key_mode_with_explicit_url(self):
        settings = AzureStorageSettings(
            auth_mode="account_key",
            account_url="https://custom.blob.core.windows.net",
            container="files",
            account_name="acct",
            account_key="k",
        )

        with patch.object(azure_module, "BlobServiceClient") as fake_service_cls:
            azure_module._build_container_client(settings)

        fake_service_cls.assert_called_once_with(
            account_url="https://custom.blob.core.windows.net",
            credential={"account_name": "acct", "account_key": "k"},
        )
        fake_service_cls.return_value.get_container_client.assert_called_once_with("files")

    def test_account_key_mode_derives_url_from_name(self):
        settings = AzureStorageSettings(
            auth_mode="account_key",
            container="files",
            account_name="acct",
            account_key="k",
        )

        with patch.object(azure_module, "BlobServiceClient") as fake_service_cls:
            azure_module._build_container_client(settings)

        kwargs = fake_service_cls.call_args.kwargs
        assert kwargs["account_url"] == "https://acct.blob.core.windows.net"
        assert kwargs["credential"] == {"account_name": "acct", "account_key": "k"}

    def test_default_credential_mode(self):
        settings = AzureStorageSettings(
            auth_mode="default_credential",
            account_url="https://acct.blob.core.windows.net",
            container="files",
        )

        with (
            patch.object(azure_module, "BlobServiceClient") as fake_service_cls,
            patch.object(azure_module, "DefaultAzureCredential") as fake_cred_cls,
        ):
            azure_module._build_container_client(settings)

        fake_service_cls.assert_called_once_with(
            account_url="https://acct.blob.core.windows.net",
            credential=fake_cred_cls.return_value,
        )
        fake_service_cls.return_value.get_container_client.assert_called_once_with("files")


class TestAzureFilesInit:
    def test_uses_injected_container_client(self):
        cc = MagicMock()
        files = AzureFiles(container_client=cc)
        assert files._container_client is cc

    def test_asserts_container_when_using_settings(self):
        settings = AzureStorageSettings(auth_mode="default_credential", account_url="https://x", container="")
        with pytest.raises(AssertionError, match="container"):
            AzureFiles(settings=settings)

    def test_reads_settings_when_not_provided(self):
        # No settings, no container_client → AzureStorageSettings.read() is called.
        with (
            patch.object(AzureStorageSettings, "read") as fake_read,
            patch.object(azure_module, "_build_container_client") as fake_build,
        ):
            fake_read.return_value = AzureStorageSettings(
                auth_mode="default_credential",
                account_url="https://x.blob.core.windows.net",
                container="files",
            )
            AzureFiles()

        fake_read.assert_called_once_with()
        fake_build.assert_called_once_with(fake_read.return_value)


class TestStoragePackageExports:
    def test_azure_classes_re_exported(self):
        from commons.storage import AzureFile as AzureFileExport
        from commons.storage import AzureFiles as AzureFilesExport

        assert AzureFileExport is AzureFile
        assert AzureFilesExport is AzureFiles


