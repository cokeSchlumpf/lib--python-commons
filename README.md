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
