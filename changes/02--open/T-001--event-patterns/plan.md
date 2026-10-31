# T-001 Event patterns: transactional outbox and live streams: plan

## Findings while planning

- **F1** The reusable `python-docs.yml` defaults to Python 3.12 as well, so `.github/workflows/docs.yml` also needs `python-version: "3.14"`; the spec named only `check.yml`.
- **F2** Three tests of the source's `test_background_workers.py` (a started conversation answered in the background, the SSE stream) depend on the conversations domain; they are not taken over. The others are rewritten on a minimal bundle `Repositories(outbox)` with a test event and handler. `test_units_of_work_for_the_current_user_notify_too` becomes "entering the factory notifies" (no `for_current_user` here).
- **F3** The source's `test_typed_live_streams.py` uses `ag_ui` and `pydantic_ai`, which are not dependencies of `commons`; the tests are rewritten with a plain Pydantic discriminated union, including a model with camelCase aliases for `by_alias`.
- **F4** The source has no tests of its own for `EventsSettings`, `background_workers_from_settings` or the envelope round trip (R3); they are written new.
- **F5** `poe check` runs mypy on `src/commons` and `src/jobs` only, not on `tests/`; the typing of `HasOutbox` (spec, concern 1) can't be proven by a test file under `poe check` as it is.
- **F6** `release-please-config.json` doesn't set `bump-minor-pre-major`, so the breaking `feat!` takes `commons` from 0.2.1 to 1.0.0 and the release moves `versions/1`; `docs/index.md` already shows `v1.0.0` and `versions/1` in its install examples.
- **F7** The local Poetry environment already runs Python 3.14.7; `pandas`, `pyodbc` and `bcrypt` in their locked versions install on it.

Deviations from the spec:

- **D1** `docs.yml` also passes `python-version: "3.14"` (F1).
- **D2** The typing of `HasOutbox` (spec, concern 1) is proven by running `poetry run mypy tests/test_events_background_workers.py` once in step 4 and reporting the result, not by `poe check`, which stays unchanged (F5). A later change can add `tests/` to mypy.

## Branching

Branch `feature/event-patterns`, draft PR #18 (`feat!: Add event patterns and require Python 3.14`). One commit per step; implementation pauses for a review after each step. The `## Migration` section is added to the PR when the change is closed.

## Steps

### 1. Python 3.14

- `pyproject.toml`: `requires-python = ">=3.14, <4.0"`; `poetry lock` refreshed. `.github/workflows/check.yml` and `docs.yml`: `python-version: "3.14"` (D1). `docs/index.md`: "requires Python 3.14 or newer". **R22**
- Proof: `poetry run poe check` and `poetry run poe docs-build` pass on 3.14; the diff of `poetry.lock` shows no new package.

### 2. Events, ports and SQL outbox

- `commons/events/event.py` (`Event` with `uuid7` ids, `EventEnvelope`), `ports.py` (`Outbox`, `HasOutbox` with a read-only `outbox`, `EventPublisher`, `EventSubscriber`, `EventConsumer`, `EventHandler`), `sql.py` (`SqlOutboxEvent` on `outbox_events`, `SqlOutbox`, private `_utc`), `__init__.py` exporting them. Google-style docstrings. **R1, R2, R3, R4, R5, R6, R9 (ports)**
- Proof: `tests/test_events_event.py` (source's `test_event.py`, plus the JSON round trip of R3 and a UUIDv7 id) and `tests/test_events_sql_outbox.py` (source's `test_sql_outbox.py` on SQLite: added only on commit, order, mark published, prune).

### 3. Broker and event logs

- `commons/events/log.py` (`EventLog`, `InMemoryEventLog`, `DeadLetter`, `FileEventLog`) and `broker.py` (`LogBroker`), copied from the source with only imports and docstrings changed. **R9 (`LogBroker` as publisher and consumer), R10, R11**
- Proof: `tests/test_events_log_broker.py`, the source's 427-line `test_log_broker.py` with imports changed (order per key, parallel keys, offsets, retries, dead letters, skipped types, file layout and name checks); a `diff` against the source in the report.

### 4. Relay, workers and settings

- `commons/events/relay.py` (`OutboxRelay` on `UnitOfWorkFactory[HasOutbox]`), `workers.py` (`BackgroundWorkers`, `Maintenance`, `CommitNotifyingUnitOfWorkFactory` on `for_user`, `for_system` and entering the factory, `CommitListener`), `settings.py` (`EventsSettings` with `extra="forbid"`, `background_workers_from_settings`). **R7, R8, R12, R13, R14, R15**
- Proof: `tests/test_events_background_workers.py` (F2: committed event handled in the background, events committed while stopped relayed at start, subscribe after start raises, maintenance prunes and runs jobs, only accepted events marked published, `stop` re-cancels and gives up, every way of opening a unit of work notifies, a failing listener doesn't fail the commit) and `tests/test_events_settings.py` (defaults without section, values from `[app.events]`, unknown key rejected, `mode` selects the log, `wake` registered as listener). `poetry run mypy` on the test module for `HasOutbox` (D2).

### 5. Live streams

- `commons/streams/live_streams.py` (`LiveStreams`, `InMemoryLiveStreams`), `typed.py` (`TypedLiveStreams`, `Codec`, `PydanticCodec`), `__init__.py`. **R16, R17, R18**
- Proof: `tests/test_streams_in_memory.py` (source's `test_in_memory_live_streams.py`) and `tests/test_streams_typed.py` (F3: prefixed key, round trip of a discriminated union, camelCase with `by_alias`).

### 6. Documentation

- `docs/api/events.md` and `docs/api/streams.md`: concepts, quickstart, configuration, usage (define, publish and handle an event; maintenance jobs; use a live stream; test), behavior and errors, from T-016 and T-018 of `lib--conversations` adapted to `commons`, plus the mkdocstrings reference; both in the `nav` of `mkdocs.yml`. **R19, R20**
- Proof: `poetry run poe docs-build` (strict) passes; `git diff main -- src/commons` touches only `events/` and `streams/` and `pyproject.toml` adds no runtime dependency (R19); review of the pages.

## Risks

- **Broker behavior drifts in the copy:** copied unchanged apart from imports and docstrings, its full test suite taken over, and a `diff` against the source in the step 3 report.
- **mypy rejects an app's bundle as `HasOutbox`:** checked in step 4 (D2); if it fails, stop and propose a fix (e.g. an explicit covariant type parameter) before going on.
- **Timing-dependent async tests are flaky in CI:** the source's tests use short polls and `asyncio.timeout`; keep their timeouts, and report any test that needed a longer one.
- **Python 3.14 breaks a dependency on CI:** found in step 1 before any new code.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 | Step 2, `test_events_event.py` |
| R2 | Step 2, `test_events_event.py` |
| R3 | Step 2, `test_events_event.py` (round trip) |
| R4 | Step 2, `test_events_sql_outbox.py` |
| R5 | Step 2, `test_events_sql_outbox.py` (SQLite); SQL Server by the column types of `commons.database` |
| R6 | Step 4, mypy on `test_events_background_workers.py` (D2) |
| R7 | Step 4, `test_events_background_workers.py` |
| R8 | Step 4, `test_events_background_workers.py` |
| R9 | Steps 2 and 3, `test_events_log_broker.py` |
| R10 | Step 3, `test_events_log_broker.py` |
| R11 | Step 3, `test_events_log_broker.py` |
| R12 | Step 4, `test_events_background_workers.py` |
| R13 | Step 4, `test_events_background_workers.py` |
| R14 | Step 4, `test_events_settings.py` |
| R15 | Step 4, `test_events_settings.py` |
| R16 | Step 5, `test_streams_in_memory.py` |
| R17 | Step 5, `test_streams_in_memory.py` |
| R18 | Step 5, `test_streams_typed.py` |
| R19 | Step 6, diff review |
| R20 | Step 6, `poe docs-build` and review |
| R21 | Steps 2–5, `poe check` |
| R22 | Step 1, `poe check` and `poe docs-build` on 3.14 |
| R23 | PR title `feat!:` (set); `## Migration` section at `close-change` |
