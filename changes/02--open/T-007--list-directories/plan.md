# T-007 List directories in Files: plan

## Findings while planning

- **F1** `SQLFiles` has no test against a real database yet; `tests/test_storage_operators.py` only checks with mocks that `create_files` returns it. The shared tests of this change run it against SQLite in a temporary folder (`sqlalchemy.create_engine("sqlite:///…")`), which also covers the new column.
- **F2** `AzureFiles` is tested only with `MagicMock` container clients (`tests/test_storage_azure.py`), as the spec assumed. azure-storage-blob 12.28 has `ContainerClient.walk_blobs(name_starts_with, include, delimiter="/")`, which yields `BlobProperties` (with `size` and `last_modified`) and `BlobPrefix` (from `azure.storage.blob`, name ending with `/`).
- **F3** `docs/api/storage.md` renders `commons.storage` with mkdocstrings (`::: commons.storage`), so new exported types and their docstrings appear without editing the page.
- **F4** No draft pull request exists for the branch yet. The developer asked for spec, plan and implementation in one go and opens the review in the pull request at the end, so the steps aren't paused for a review and the pull request is opened once all steps are done.
- **F5** The checks are green before the change: `poetry run poe check` passes with 549 tests.

Deviations from the spec:

- None.

## Branching

Branch `feature/list-directories` (worktree `.claude/worktrees/list-directories`), one pull request `feat(storage): list directories and file metadata in Files`, squash-merged. As the developer asked, the steps are implemented one after the other without a review in between, each as its own commit; the developer reviews the whole pull request.

## Steps

### 1. Types and default implementations

- `Directory`, `DirectoryListing` in `files.py`, exported from `commons.storage`. **R2, R13**
- `File.size` (length of the content) and `File.last_modified` (`None`) as concrete properties. **R8, R11**
- `Files.list_directory(path="/")` as a concrete method built on `list`, sorted, with whole-segment matching and empty results for missing paths. **R1, R2, R3, R4, R7**
- Proof: `tests/test_storage_directories.py` with a minimal `Files`/`File` subclass in memory (only the abstract methods): one level, sorted, `/foo` vs `/foo-bar`, `/foo/` vs `/foo`, root, file key and missing key give an empty listing, default `size` and `last_modified`.

### 2. LocalFiles and SQLFiles

- `LocalFiles.list_directory` with `iterdir` and subfolders only if they contain a file; `LocalFile.size` and `last_modified` from `stat`. **R1–R5, R8, R9**
- `SQLFiles`: column `last_modified` set on every `put`, read as UTC; `SQLFile.size` from the data; `list_directory` from the default; `# shortcut:` on loading the bytes. **R5, R8, R9, R10**
- Proof: the shared cases of step 1 parametrized over `LocalFiles` and `SQLFiles`, plus: size and `last_modified` (UTC, not `None`) for `find` and both listings, `last_modified` later after an overwrite, an empty local folder isn't listed.

### 3. AzureFiles and FilesWithPrefix

- `AzureFiles.list_directory` with one `walk_blobs` call; `AzureFile` with optional `size`/`last_modified`, filled from the listing and from `find`, fetched once if missing. **R5, R6, R8, R9**
- `FilesWithPrefix.list_directory` delegating with the prefix stripped; `_PrefixedFile` delegating `size`/`last_modified`. **R5, R8**
- Proof: the shared cases parametrized over `AzureFiles` with an in-memory fake `ContainerClient` and over `FilesWithPrefix`; a test that `list_directory` calls `walk_blobs` once and no `list_blobs`; a test that metadata from the listing doesn't call `get_blob_properties` or `download_blob`.

### 4. Docs and checks

- Docstrings of the new types and methods; a short section in the module docstring or `docs/api/storage.md` on directories and metadata, including the note on existing `SQLFiles` tables. **R13**
- Proof: `poetry run poe check` (all existing tests unchanged, **R12**) and `poetry run poe docs-build`.

## Risks

- **The Azure fake differs from the real service:** keep it to the documented behaviour (F2) and sort in our code; noted for the review (spec, concern 1).
- **Existing `SQLFiles` tables break:** accepted in the intent; documented in the docs and the pull request.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 | Steps 1–3, shared listing tests |
| R2 | Steps 1–3, nested and empty-folder tests |
| R3 | Steps 1–3, sorting test |
| R4 | Steps 1–3, path tests (`/foo-bar`, trailing slash, root, file key, missing key) |
| R5 | Steps 2–3, same tests parametrized over all four backends |
| R6 | Step 3, `walk_blobs` call test |
| R7 | Step 1, minimal `Files` subclass |
| R8 | Steps 1–3, metadata tests per backend |
| R9 | Steps 2–3, metadata without `open`/`download_blob` |
| R10 | Step 2, overwrite test (parametrized) |
| R11 | Step 1, minimal `File` subclass |
| R12 | Step 4, existing tests unchanged in `poe check` |
| R13 | Steps 1 and 4, export and `docs-build` |
