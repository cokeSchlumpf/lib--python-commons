<!-- core-agent-skills:begin -->
## Working in this repository

Shared rules, written by `core-tools update-claude-md` (plugin `core-agent-skills` of core--platform); don't edit them here.

### Changes

- Every change goes through `changes/` (see `changes/README.md`): intent, spec, plan, each accepted by the developer before the next one is written. Use the skills `start-change`, `specify-change`, `plan-change` and `close-change`.
- No code before the plan is accepted. Implement one step at a time and stop for a review after each step.
- Only an explicit "yes" is acceptance; a hedged answer ("yes, but I need to look into it") is not. Ask.

### Git and pull requests

- Never commit to `main`. One branch per change (`feature/<slug>`, `ci/<slug>` for workflow-only changes).
- Commit only when the developer asks for it, and never with co-authoring or AI attribution (`Co-Authored-By: …`, "Generated with …"), neither in commits nor in pull requests.
- Pull requests are squash-merged; their title is a conventional commit header (`feat: …`, `fix: …`; `feat!: …` and a `## Migration` section for breaking changes), as it becomes the commit message release-please derives the changelog and the version from. Open them with the skill `create-pull-request`.

### GitHub

- Never change anything on GitHub (repositories, settings, rulesets, pull requests) without asking first.
- Access it only through `git` and `gh`, with the developer's own login. Never ask for, show or pass a token.

### Writing

- Markdown: one paragraph or list item per line, no hard wraps.
- Change documents have no front matter and no metadata lines (the folder names them, Git dates them).

### Code

Details: `core--docs/notes/2026-10-28-0950--smallest-complete-change.md` of core--platform.

- Make the smallest change that fully solves the task: use what the codebase and our own libraries already offer, then the standard library, then installed dependencies. No new dependency for a few lines.
- Use an internal library only if `core-tools list-libraries` lists it on a `versions/<major>` branch; any other needs the developer's consent.
- No speculative code: no features, options, abstractions or configuration nobody asked for. Keep the existing structure and conventions.
- Finish the change: update every caller, test and fixture it affects. Fix a bug at its root, after checking every caller.
- Never cut validation at trust boundaries, security, error handling that prevents data loss, or anything the developer asked for. Mark a shortcut with a known limit: `# shortcut: <the limit>, <when to upgrade>`.
- End each report with what you skipped or didn't check, and the risks.

### Libraries

Details: `core--docs/notes/2026-10-30-1905--python-libraries-on-github.md` of core--platform.

- What the packages export is the public API, and a promise: consumers use `versions/<major>`. Breaking it is a `feat!` with a `## Migration` section; prefer an addition.
- Internal libraries are referenced on `versions/<major>`, never copied.
<!-- core-agent-skills:end -->

## lib--python-commons

- Common functionality used across apps and other libraries; published as `commons` on `versions/<major>`.
- `src/commons`: the operators (`*_operators.py`), `settings`, `database`, `storage`, `users`, `datastructures`; `src/jobs`: background jobs; `tests/`: pytest; `docs/`: the mkdocs site.
- `azure` is an optional extra: `poetry install --all-extras --with docs`.
- Checks: `poetry run poe check` (lint, types, tests) and `poetry run poe docs-build`; `poetry run poe fix` formats.
