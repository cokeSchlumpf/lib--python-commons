"""A file storage abstraction with local, SQL and Azure Blob Storage backends.

- **Files** (`Files`, `File`): files by key, an absolute slugified path such as ``/cases/123/report.pdf``; `find`,
  `get`, `list` (every file below a path, recursively), `put` and `delete`.
- **Directories** (`Files.list_directory`, `DirectoryListing`, `Directory`): the directories and files directly below
  a path, e.g. for a file browser. Directories are virtual: one exists as long as a file is stored below it, so there
  are no empty directories and nothing to create or delete.
- **Metadata** (`File.size`, `File.last_modified`): known by every backend without reading the file. Metadata with a
  domain meaning (title, owner, tags, permissions, content type) belongs to the application, linked by the key.
- **Backends** (`LocalFiles`, `SQLFiles`, `AzureFiles`) and `FilesWithPrefix`, which puts every key below a prefix,
  e.g. one per tenant. `SQLFiles` tables created before commons 1.4 have no column ``last_modified`` and aren't
  migrated: drop the table or add the column by hand.
"""

from .azure import AzureFile, AzureFiles
from .files import Directory, DirectoryListing, File, Files
from .local import LocalFile, LocalFiles
from .prefix import FilesWithPrefix
from .sql import SQLFile, SQLFiles

__all__ = [
    "AzureFile",
    "AzureFiles",
    "Directory",
    "DirectoryListing",
    "File",
    "Files",
    "FilesWithPrefix",
    "LocalFile",
    "LocalFiles",
    "SQLFile",
    "SQLFiles",
]
