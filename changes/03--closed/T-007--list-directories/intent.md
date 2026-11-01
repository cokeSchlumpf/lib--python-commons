# T-007 List directories in Files

## Problem

Apps need to show stored files in a file browser with folders: open a folder, see its subfolders and files, go one level deeper. `commons.storage.Files` can't do that today. `Files.list(path)` only returns all files below `path`, recursively, as a flat list. There are no folders and no way to stop at one level. Every app would have to load the whole tree and derive the folders from the keys itself. With Azure Blob Storage that means listing every blob below the path on every click, so it gets slower and costs more as the data grows. A file browser also needs at least the size and the date of a file. `File` only has `key` and `open()` today, so an app would have to open or download each file to show those.

## Proposed outcome

- `Files` can list one level of a path: the folders and files directly below it, without loading the files below the subfolders.
- Folders are virtual: a folder exists as long as at least one file is stored below it. There are no empty folders, and creating or deleting folders explicitly isn't part of this change.
- Every backend supports it (`LocalFiles`, `AzureFiles`, `SQLFiles`, `FilesWithPrefix`) and they behave the same. Azure lists a level on the server (`walk_blobs` with delimiter `/`), not by loading everything.
- Folders and file metadata come in this one change, because a file browser needs both and both touch the same listing code in every backend.
- `File` has `size` (bytes) and `last_modified` as properties, filled by the listing without opening the file. These come from the backend: Azure returns them with every listed blob, the local file system from `stat`, SQL from `length(data)` and a new column for `last_modified`.
- Everything with domain meaning stays in the apps, linked by the key: title, owner, tags, permissions, and also the content type. `Files` doesn't store it.
- A listing has no paging for now. The return type is chosen so that paging can be added later without breaking the API (decided in the spec).
- `Files.list(path)` keeps working as it does today (recursive, files only).

## Affected users and systems

- **Apps with a file browser (app--casesight and others on the core--platform standard):** they can build folder navigation on `Files` instead of their own key parsing.
- **lib--python-commons, `commons.storage`:** new methods or types on `Files`/`File` and in each backend, plus tests and docs.
- **Existing users of `Files`:** none in the apps today, as far as a search of the local app repositories shows. Existing calls must still work unchanged.

## Constraints

- Backwards compatible: a minor release of `versions/1`. Existing signatures and the behaviour of `list`, `find`, `get`, `put` and `delete` don't change.
- Same semantics in all backends, covered by shared tests that run against every backend.
- Keys stay as they are: slugified absolute paths starting with `/`, and only whole path segments match (`/foo` doesn't match `/foo-bar`).
- The table of `SQLFiles` may change (for example a new column for `last_modified`). That doesn't count as a breaking change, and existing tables don't need a migration.

## Open questions

None.
