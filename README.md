# Commons

Common functionalities which are used across a broad range of apps and other libs.

📖 **Documentation:** https://cokeschlumpf.github.io/lib--python-commons/

## Development

```bash
poetry install --all-extras --with docs
poetry run poe check        # linting, type checks and tests (same as CI)
poetry run poe fix          # auto-fix lint issues and format code
```

## Documentation

The documentation is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) and
[mkdocstrings](https://mkdocstrings.github.io/). The API reference is generated from the docstrings in `src/`.

| Path | Purpose |
| --- | --- |
| `mkdocs.yml` | Site configuration and navigation (`nav`) |
| `docs/index.md` | Landing page including the module overview table |
| `docs/api/*.md` | One page per module/package of the API reference |
| `.github/workflows/docs.yml` | Builds and deploys the site to GitHub Pages on every push to `main` |

```bash
poetry run poe docs         # serve locally with live reload on http://127.0.0.1:8000
poetry run poe docs-build   # strict build into site/ (same as CI)
```

The strict build also runs in the **Check** workflow on `feature/` and `fix/` branches, so a broken reference fails
the pipeline before it reaches `main`.

## Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please) and based on
[Conventional Commits](https://www.conventionalcommits.org/). See the [changelog](CHANGELOG.md) for all releases.

- **Tags** `vX.Y.Z` (e.g. `v1.0.4`), each with a GitHub Release.
- **Branches** `versions/<major>` (e.g. `versions/1`) always point to the latest release of that major version.
- **`version`** in `pyproject.toml` and **`CHANGELOG.md`** (newest release on top) are updated automatically.

### PR titles are commit messages

PRs are squash-merged, so the **PR title** becomes the commit on `main` and decides the next version. The
**PR Title** check rejects titles that aren't conventional commits.

| PR title | Release | In changelog |
| --- | --- | --- |
| `feat: …` | minor (`1.2.0` → `1.3.0`) | Features |
| `fix: …`, `perf: …`, `deps: …` | patch (`1.2.0` → `1.2.1`) | Bug Fixes, Performance Improvements, Dependencies |
| `feat!: …` or a `BREAKING CHANGE: …` line in the PR description | major (`1.2.0` → `2.0.0`) | as above, marked as breaking |
| `docs: …`, `revert: …` | patch | Documentation, Reverts |
| `ci:`, `chore:`, `test:`, `build:`, `style:`, `refactor:` | none on their own | hidden |

### How a release happens

1. Every merge to `main` creates or updates a single **Release PR** (`chore(main): release X.Y.Z`). It contains the
   version bump and the new changelog section and collects all changes since the last release.
2. **Merge the Release PR whenever you want to release**, e.g. once a meaningful set of changes has built up, or
   right away for an urgent fix. Merging it creates the tag, the GitHub Release and moves `versions/<major>`.

The Release PR is regenerated on every push to `main`, so manual edits to it are overwritten. Make final edits right
before merging.

**Optional LLM polish:** if the repo secret `OPENAI_API_KEY` is set, `scripts/polish_changelog.py` adds a
*Highlights* summary to the Release PR and rewords the entries. Review it in the Release PR. Every entry and link is
kept; if the output doesn't pass validation or the API fails, the generated notes stay unchanged.

### Fixing versions and release notes

- **Force a version:** add `Release-As: 2.0.0` as the last line of a PR description before merging it.
- **Fix a wrongly titled PR after merging:** edit the merged PR's description and add the corrected message; it's
  used the next time the Release PR is generated:

  ```
  BEGIN_COMMIT_OVERRIDE
  feat: the corrected commit message
  END_COMMIT_OVERRIDE
  ```

### Repository settings

The pipeline relies on these GitHub settings:

- **Settings → General → Pull Requests:** only *Allow squash merging* enabled, with *Default commit message* set to
  **Pull request title and description**. Otherwise single-commit PRs use the commit message instead of the PR title,
  and `BREAKING CHANGE:` / `Release-As:` lines in the description don't reach `main`.
- **Settings → Rules → Rulesets:** a branch ruleset for `versions/*` with *Restrict deletions* and *Block force
  pushes*.
- **Settings → Secrets and variables → Actions:** `OPENAI_API_KEY` (optional, enables the LLM polish).

## Maintenance Tasks

### Adding a new module or package

New code does **not** show up in the documentation automatically. For every new public module or package:

- [ ] **Make it importable.** Packages need an `__init__.py` (namespace packages can't be resolved by mkdocstrings).
  For packages, export the public API via `__all__` in `__init__.py`, since only exported names appear on the
  package's page.
- [ ] **Create an API page** in `docs/api/`, e.g. `docs/api/my-module.md`:

  ```markdown
  # My module

  ::: commons.my_module
  ```

  Several modules can share a page by adding one `:::` line each (see `docs/api/jobs.md`).
- [ ] **Add the page to `nav`** in `mkdocs.yml` under `API reference`, in the section that fits best.
- [ ] **Add a row to the module table** in `docs/index.md`.
- [ ] **Run `poe docs-build`** and check the page with `poe docs`.

### Renaming, moving or removing a module

- [ ] Update the `:::` path in the corresponding `docs/api/*.md` page (or delete the page).
- [ ] Update `nav` in `mkdocs.yml` and the module table in `docs/index.md`.

### Writing docstrings

- Use [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) (`Args:`,
  `Returns:`, `Raises:`, `Example:`). Docstrings are rendered as Markdown.
- Link to other objects with mkdocstrings cross-references using the full import path, e.g.
  `` [`Files`][commons.storage.Files] ``. Don't use Sphinx roles such as ``:class:`Files` ``, they are rendered as
  plain text.
- Objects without docstrings are still listed (signature only), but a short docstring makes the reference far more
  useful.
