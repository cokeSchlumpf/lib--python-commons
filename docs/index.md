# Commons

`commons` is a library of common functionality that is used across a broad range of apps and other libraries.
It bundles small, well-tested helpers (string, dict, date & time operators, …) with larger building blocks for
settings, database access, file storage, user management and background jobs.

## Installation

The library is installed directly from GitHub and requires Python 3.12 or newer. Pin it to a release tag
(e.g. `v1.0.0`) or follow a major version with its branch (e.g. `versions/1`, always the latest `1.x` release).
All releases are listed in the [changelog](changelog.md).

=== "Poetry"

    ```bash
    # exact release
    poetry add "git+https://github.com/cokeSchlumpf/lib--python-commons.git#v1.0.0"

    # latest 1.x release (update with `poetry update commons`)
    poetry add "git+https://github.com/cokeSchlumpf/lib--python-commons.git#versions/1"

    # including the Azure storage backend
    poetry add "git+https://github.com/cokeSchlumpf/lib--python-commons.git#v1.0.0[azure]"
    ```

=== "pip"

    ```bash
    # exact release
    pip install "commons @ git+https://github.com/cokeSchlumpf/lib--python-commons.git@v1.0.0"

    # latest 1.x release
    pip install "commons @ git+https://github.com/cokeSchlumpf/lib--python-commons.git@versions/1"

    # including the Azure storage backend
    pip install "commons[azure] @ git+https://github.com/cokeSchlumpf/lib--python-commons.git@v1.0.0"
    ```

## What's inside

| Module | Description |
| --- | --- |
| [`commons.collection_operators`](api/collection-operators.md), [`commons.datetime_operators`](api/datetime-operators.md), [`commons.dict_operators`](api/dict-operators.md), [`commons.string_operators`](api/string-operators.md), [`commons.url_operators`](api/url-operators.md), [`commons.path_operators`](api/path-operators.md) | General-purpose helper functions. |
| [`commons.excel_operators`](api/excel-operators.md) | Writing pandas data frames to formatted Excel workbooks. |
| [`commons.datastructures.tree`](api/tree.md) | A generic tree structure with rendering helpers. |
| [`commons.settings`](api/settings.md) | Reading layered app settings from TOML files and `APP__` environment variables. |
| [`commons.database`](api/database.md), [`commons.database_operators`](api/database-operators.md) | SQLModel/SQLAlchemy building blocks: column types, table mixins, unit of work. |
| [`commons.storage`](api/storage.md), [`commons.storage_operators`](api/storage-operators.md) | A file storage abstraction with local, SQL and Azure Blob Storage backends. |
| [`commons.users`](api/users.md) | User identities and role-based access control. |
| [`jobs`](api/jobs.md) | Running and tracking background jobs. |

## Contributing

Checks and formatting are run with [Poe the Poet](https://poethepoet.natn.io/):

```bash
poetry install --all-extras --with docs
poetry run poe check      # linting, type checks and tests
poetry run poe fix        # auto-fix lint issues and format code
poetry run poe docs       # serve this documentation locally on http://127.0.0.1:8000
```
