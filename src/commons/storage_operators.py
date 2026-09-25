"""Storage backend factory."""

from commons import settings
from commons.storage import AzureFiles, LocalFiles, SQLFiles
from commons.storage.files import Files
from sqlalchemy import Engine


def create_files(engine: Engine | None = None) -> Files:
    """Construct a :class:`Files` instance from configured :class:`StorageSettings`.

    Dispatches on :attr:`StorageSettings.mode`:

    - ``local``: returns :class:`LocalFiles`. Root is ``StorageSettings.local.root``
      if set, otherwise ``AppSettings.data_dir / "files"``.
    - ``sql``: returns :class:`SQLFiles` (which pulls its engine from
      :class:`DatabaseSettings` via :func:`database_operators.create_engine`).
    - ``azure``: returns :class:`AzureFiles` constructed from
      ``StorageSettings.azure``.
    """

    storage_settings = settings.StorageSettings.read()

    if storage_settings.mode == "azure":
        assert storage_settings.azure is not None, "Azure storage settings must be present, if mode is azure."
        return AzureFiles(storage_settings.azure)

    if storage_settings.mode == "sql":
        return SQLFiles(engine)

    # local (default)
    root = None
    if storage_settings.local and storage_settings.local.root:
        root = storage_settings.local.root
    return LocalFiles(root=root)
