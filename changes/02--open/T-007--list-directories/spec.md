# T-007 List directories in Files: spec

## Requirements

### Listing one level

- **R1** `Files.list_directory(path="/")` returns a `DirectoryListing` with the directories and the files directly below `path`, not the ones further down.
- **R2** A directory is listed with its key (`/foo/bar`, no trailing slash) as a `Directory`. It exists only while at least one file is stored below it, at any depth. Empty directories are never listed.
- **R3** Directories and files are each sorted by key, ascending.
- **R4** `path` is matched by whole segments as in `list` (`/foo` doesn't list `/foo-bar/…`). `/foo` and `/foo/` are the same path, `/` and `""` are the root. A path with nothing below it (a file key, or a key that doesn't exist) returns an empty listing, not an error.
- **R5** `LocalFiles`, `SQLFiles`, `AzureFiles` and `FilesWithPrefix` return the same listing for the same stored files. `FilesWithPrefix` returns keys without its prefix.
- **R6** `AzureFiles.list_directory` lists one level on the server (one `walk_blobs` call with delimiter `/`), not by listing every blob below the path.
- **R7** A subclass of `Files` outside commons that only implements the existing abstract methods still works and gets a correct `list_directory`.

### File metadata

- **R8** Every `File` has `size` (bytes, `int`) and `last_modified` (`datetime` with time zone UTC, or `None` if the backend doesn't know it).
- **R9** For files returned by `find`, `get`, `list` and `list_directory` of the four backends, both are known (`last_modified` isn't `None`) and reading them doesn't download or read the file's bytes. (`SQLFiles` loads the bytes with every query today; see concern 2.)
- **R10** `last_modified` changes when a file is overwritten with `put`.
- **R11** A subclass of `File` outside commons that only implements `key` and `open` still works: its `size` is the length of its content, its `last_modified` is `None`.

### Compatibility

- **R12** `list`, `find`, `get`, `put` and `delete` keep their signatures and behaviour; all existing tests pass unchanged.
- **R13** `Directory` and `DirectoryListing` are exported from `commons.storage` and documented in the API docs.

## Design

New types in `commons/storage/files.py`, exported from `commons.storage`:

```python
@dataclass(frozen=True)
class Directory:
    key: str                     # "/foo/bar"

@dataclass(frozen=True)
class DirectoryListing:
    directories: list[Directory]
    files: list[File]
```

`DirectoryListing` is the return type so that paging can be added later as a further field (e.g. a continuation token) without changing the signature.

`File` gets two concrete (not abstract) properties, so existing subclasses keep working (R11):

```python
@property
def size(self) -> int:                     # default: len(self.open().getvalue())
@property
def last_modified(self) -> datetime | None:  # default: None
```

`Files` gets a concrete `list_directory(path="/")`. Its default implementation is built on `self.list(path)`: for each file key below the path, the first segment after the path is either a file (no further `/`) or a directory. That gives every subclass a correct result (R7) and is what `SQLFiles` uses. The other backends override it:

| Backend | `list_directory` | `size` / `last_modified` |
| --- | --- | --- |
| `LocalFiles` | `iterdir()` of the folder; a subfolder is listed only if `rglob` finds a file in it (R2) | `stat()` of the path: `st_size`, `st_mtime` as UTC |
| `AzureFiles` | `walk_blobs(name_starts_with=prefix, delimiter="/")`: `BlobPrefix` items are directories (trailing `/` removed), `BlobProperties` items are files | from the `BlobProperties` of the listing or of `get_blob_properties` in `find`; an `AzureFile` created without them fetches them once on first access |
| `SQLFiles` | default implementation | `size` is `len(data)`; `last_modified` from a new column |
| `FilesWithPrefix` | delegates to the inner `list_directory` with the prefix added and strips it from directory and file keys | `_PrefixedFile` delegates both |

`SQLFiles`: the table `files` gets the column `last_modified` (`DateTime(timezone=True)`, not null), set to the current UTC time on every `put` (insert and update). SQLite returns naive datetimes, so values without a time zone are read as UTC. As agreed in the intent, existing tables aren't migrated: a table created before this change has to be dropped or get the column by hand.

The `AzureFile` constructor gets optional keyword arguments `size` and `last_modified`; `AzureFile(key, container_client)` keeps working. `LocalFile` and `SQLFile` keep their constructors; `SQLFile` gets an optional keyword argument `last_modified`.

Tests: one parametrized test module (`tests/test_storage_directories.py`) runs the same cases for R1–R5 and R8–R10 against `LocalFiles`, `SQLFiles` (SQLite in memory), `FilesWithPrefix` and `AzureFiles` with an in-memory fake of the `ContainerClient` (the existing Azure tests use mocks too; there's no Azurite in the checks). An Azure test checks that `list_directory` calls `walk_blobs` once and never `list_blobs` (R6). A minimal subclass of `Files` and `File` in the test covers R7 and R11.

## Alternatives considered

- **Add `recursive: bool` to `list`:** `list(path, recursive=False)` would return only files and has no place for directories without changing the return type, which would break callers.
- **Abstract `list_directory`, `size` and `last_modified`:** forces every backend to implement them, but breaks any subclass of `Files` or `File` outside commons, and that would be a breaking change of the public API.
- **Return a flat list of entries (`list[File | Directory]`):** one list is harder to page later and makes callers sort entries by type themselves; two lists in a result object are clearer.
- **Real directories (create, delete, empty directories):** blob storage has none. Simulating them needs marker blobs, and the intent excludes it.
- **Metadata in the apps:** the apps would need their own bookkeeping that can drift from the stored files, and Azure delivers the values with the listing anyway (intent Q1).

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Backwards compatible, minor release of `versions/1` | R7, R11, R12; additions only, concrete defaults instead of abstract methods; PR title `feat(storage): …` |
| Same semantics in all backends, shared tests | R5; one parametrized test module for all backends |
| Keys stay as they are, whole segments match | R2, R4 |
| `SQLFiles` table may change, no migration | Design: new column `last_modified`, no migration |
| Domain metadata stays in the apps | R8 provides only `size` and `last_modified`; Out of scope |
| No paging for now, extensible later | `DirectoryListing` as result object (Design) |

## Open questions

None. The developer asked for spec, plan and implementation in one go and reviews them in the pull request.

## Areas of concern

1. **Azure behaviour only tested against a fake** (R6, R9): the fake might not match the real `walk_blobs` (e.g. the order, or `BlobPrefix` names). Handled by keeping the fake to the documented behaviour (prefix names end with `/`) and sorting in our code (R3). A test against Azurite or a real container isn't part of this change. Owner: Michael Wellner.
2. **`SQLFiles` loads all bytes when listing** (R9): `list` already reads every row with its data, and the default `list_directory` builds on it. Fine for the small tables `SQLFiles` is used for; marked as `# shortcut:` in the code. Owner: Michael Wellner.
3. **Existing `SQLFiles` tables** (Design): an existing table without the column makes `put` and queries fail. Agreed in the intent; noted in the docstring of `SQLFiles` and in the PR. Owner: Michael Wellner.
4. **Azure accounts with hierarchical namespace** (R2): there, folders are their own entries, and an empty folder may show up as a blob without content, so it could be listed as a file. Files written through `Files` never create such folders; folders created with other tools aren't handled and this isn't tested. Owner: Michael Wellner.

## Out of scope

- Creating, renaming or deleting directories explicitly, and empty directories.
- Paging of listings.
- Further metadata: content type, ETag, custom blob metadata, and anything with domain meaning (title, owner, tags, permissions); those stay in the apps, linked by the key.
- Faster `SQLFiles` queries (filtering in SQL, not loading the bytes).
