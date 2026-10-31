# T-001 Event patterns: transactional outbox and live streams: spec

## Requirements

### Events

- **R1** `Event` is the base of all events: an immutable Pydantic model with the class attributes `topic` and `event_type`, the fields `event_id` (a new UUIDv7 string by default) and `occurred_at` (aware UTC, now by default), and an overridable property `key` (`None` by default).
- **R2** `Event.to_envelope()` returns an `EventEnvelope` with the fields `event_id`, `topic`, `key`, `event_type`, `occurred_at` and `payload` (the event as JSON), and `Event.from_envelope(envelope)` returns the typed event; it raises `ValueError` if the envelope's topic or event type differs, or its payload does not validate.
- **R3** An envelope survives its JSON form: `EventEnvelope.model_validate_json(envelope.model_dump_json())` equals the envelope, and `from_envelope` of it equals the event.

### Outbox

- **R4** The `Outbox` port stores events in the unit of work of the caller (`add_event`), lists unpublished events in the order they were added (`list_unpublished(limit)`), marks events published (`mark_published(event_ids, published_at)`, unknown ids ignored), and deletes events published before a time (`delete_published_before(before)`, returning the count).
- **R5** `SqlOutbox(session)` implements `Outbox` on the table `outbox_events` (columns as in both copies: `sequence`, `event_id` unique, `topic`, `key`, `event_type`, `occurred_at`, `payload`, `published_at` indexed); it never commits, so an event is stored if and only if the caller's unit of work commits. It runs on SQLite and SQL Server.
- **R6** `HasOutbox` is the protocol of a repository bundle with an `outbox`; any app's bundle that has an `outbox: Outbox` (e.g. a dataclass) satisfies it without inheriting from it.

### Relay

- **R7** `OutboxRelay(repositories, publisher, poll_interval, batch_size, retention)` takes any `UnitOfWorkFactory` whose bundle satisfies `HasOutbox`; `run()` publishes all unpublished events at start, then whenever `wake()` is called or `poll_interval` passed, oldest first, and marks each published only after the publisher accepted it.
- **R8** `wake()` can be called from any thread and does nothing when the relay is not running; `prune()` deletes the events published longer ago than `retention` and returns the count.

### Broker

- **R9** `EventPublisher` (`publish(envelope)`), `EventSubscriber` (`subscribe(group, event_type, handler)`, `ValueError` for a second handler of the same type in a group), `EventConsumer` (a subscriber with `run()`) and `EventHandler[E]` (an async callable taking the typed event) are the ports of a message broker.
- **R10** `LogBroker(log, poll_interval, batch_size, max_concurrency, max_attempts, retry_backoff)` implements `EventPublisher` and `EventConsumer` on an `EventLog`, with the behavior of the `lib--conversations` version: every subscribed group gets every event at least once; events with the same key in order, others in parallel up to `max_concurrency`; an offset is committed only past events that are all processed; a failing handler is retried up to `max_attempts`, then dead-lettered; an unreadable event is dead-lettered at once; events without a handler in the group are skipped.
- **R11** `EventLog` is the port of the broker's storage (append, read from an offset, committed offsets per group and topic, dead letters); `InMemoryEventLog` keeps it in memory (with `dead_letters` of `DeadLetter` for tests), `FileEventLog(root)` in files (`<topic>.jsonl`, `_offsets/<group>/<topic>.json`, `_dead_letters/<group>/<topic>.jsonl`), rejecting topic and group names that are not safe file names.

### Background workers and settings

- **R12** `BackgroundWorkers(relay, consumer, maintenance, maintenance_interval)` starts the relay, the consumer and the maintenance (outbox pruning, then the given jobs, at start and every `maintenance_interval`) on the running event loop with `start()`, restarts a crashed task, and stops them with `stop(timeout)` without ever blocking longer than `timeout`; `subscribe` after `start`, or a second `start`, raises `RuntimeError`.
- **R13** `CommitNotifyingUnitOfWorkFactory(inner)` wraps any `UnitOfWorkFactory[T]` and calls the listeners added with `add_commit_listener` after every successful commit of a unit of work opened with `for_user`, `for_system` or by entering the factory; a failing listener is logged and never fails the commit.
- **R14** `EventsSettings` reads `[app.events]` with the keys and defaults of `lib--conversations` (`mode` `file`/`memory`, `dir`, `poll_interval_seconds`, `handler_max_concurrency`, `handler_max_attempts`, `outbox_retention_days`, `maintenance_interval_seconds`), the defaults if the section is missing, and rejects unknown keys.
- **R15** `background_workers_from_settings(repositories, settings, maintenance)` wires the log and broker of `settings.mode`, the relay and the workers, and adds `relay.wake` as commit listener if `repositories` is a `CommitNotifyingUnitOfWorkFactory`.

### Live streams

- **R16** The `LiveStreams` port appends byte payloads to a stream by key (`append`, `ValueError` on a closed stream), closes it (`close`, twice is a no-op) and reads it (`read(key, after, wait)`) from after a position to its end, then live until it is closed, for every reader; positions are opaque, increasing strings; an invalid position raises `ValueError`.
- **R17** `InMemoryLiveStreams(retention)` implements `LiveStreams` in process memory: positions `"1"`, `"2"`, …; a closed stream stays readable for `retention` seconds, then disappears; with `wait=False`, reading a missing stream ends at once.
- **R18** `TypedLiveStreams[T](streams, prefix, codec)` reads and writes values of `T` on the stream `"<prefix>:<id>"`; `Codec[T]` is the port of encoding, `PydanticCodec[T](type_, by_alias)` encodes models and discriminated unions as JSON.

### Package, documentation and checks

- **R19** Everything above is exported from `commons.events` (R1–R15) and `commons.streams` (R16–R18); nothing existing in `commons` changes, and no runtime dependency is added.
- **R20** The mkdocs site has a page per package with concepts, a quickstart, configuration, usage (define, publish and handle an event; use a live stream; test), behavior and errors, and the API reference; `poe docs-build` passes.
- **R21** The tests of the `lib--conversations` copy for these parts are taken over and pass with `poe check`.

### Python version

- **R22** `commons` requires Python 3.14 or later (`requires-python = ">=3.14, <4.0"`); the check workflow runs on Python 3.14, and the documentation names 3.14 as the minimum.
- **R23** The pull request is marked breaking (`feat!:`) with a `## Migration` section: consumers raise their own `requires-python` to `>=3.14` before moving to the new major version.

## Design

### Packages

Two packages, laid out like `commons.storage` and `commons.users`: plain modules, the port next to its adapters, and everything public re-exported in the package's `__init__.py`.

```text
src/commons/events/
  __init__.py      exports of R1–R15
  event.py         Event, EventEnvelope
  ports.py         Outbox, HasOutbox, EventPublisher, EventSubscriber, EventConsumer, EventHandler
  sql.py           SqlOutboxEvent (table outbox_events), SqlOutbox
  relay.py         OutboxRelay
  log.py           EventLog, InMemoryEventLog, DeadLetter, FileEventLog
  broker.py        LogBroker
  workers.py       BackgroundWorkers, Maintenance, CommitNotifyingUnitOfWorkFactory, CommitListener
  settings.py      EventsSettings, background_workers_from_settings
src/commons/streams/
  __init__.py      exports of R16–R18
  live_streams.py  LiveStreams, InMemoryLiveStreams
  typed.py         TypedLiveStreams, Codec, PydanticCodec
```

The module names are a proposal for the plan; the public API is what `__init__.py` exports.

### Taking over the code

The code is taken from `lib--conversations` (GitHub `main`) with its behavior and tests, and changed only where this repository requires it:

- **Imports:** `utc_now` from `commons.datetime_operators`; the domain types (`ConversationRepositories`) become `HasOutbox`; the private `_utc` helper (aware datetimes from `UTCDateTime`) moves into `sql.py`.
- **Event ids:** `event_id` is a `str` defaulting to `str(uuid7())` from the standard library, as in `lib--conversations`; this is why `commons` moves to Python 3.14 (R22). Order still comes from the outbox `sequence` and the log offsets, not from the id. The other ids of `commons` (`EntityMixin`, users, jobs) keep `uuid4` here; moving them is backlog item T-002.
- **Unit of work:** `CommitNotifyingUnitOfWorkFactory` wraps `for_user`, `for_system` and entering the factory, the API of this `commons`; `for_current_user` of the other `commons` is not added.
- **Docstrings:** Google style (`Args:`, `Raises:`), as the mkdocs configuration and the rest of `commons` expect; the doctest of `PydanticCodec` uses a plain Pydantic model instead of `ag_ui`.
- **Tests:** `tests/test_events_*.py` and `tests/test_streams_*.py`, flat as the existing tests; async tests with `asyncio.run`, as in the source, so no `pytest-asyncio` is needed.

### Wiring in an app

```python
@dataclass
class Repositories:          # the app's bundle; satisfies HasOutbox
    invoices: InvoicesRepository
    outbox: Outbox

repositories = CommitNotifyingUnitOfWorkFactory(
    SqlUnitOfWorkFactory(sessionmaker(bind=engine, class_=Session), lambda s, u: Repositories(SqlInvoices(s), SqlOutbox(s)))
)
workers = background_workers_from_settings(repositories)        # [app.events]
workers.subscribe(group="invoice-validation", event_type=AnalysisRunRequested, handler=...)
# lifespan: workers.start() / await workers.stop()
```

A library such as `lib--conversations` offers its own bundle with an `outbox` built from the app's session and its handlers as `subscribe_*(workers, …)`; its events go into the app's one `outbox_events` table on its own topics.

`HasOutbox` declares `outbox` as a read-only property, so a dataclass field `outbox: Outbox` (or `SqlOutbox`) satisfies it, and `UnitOfWorkFactory[Repositories]` is accepted where `UnitOfWorkFactory[HasOutbox]` is expected (its type parameter is only returned, so mypy infers it covariant).

### Table

`SqlOutboxEvent` is a `SQLModel` table like `commons.storage.SQLFile` and the user tables: importing `commons.events` registers `outbox_events` on `SQLModel.metadata`, and the app's `create_all` creates it. The name and columns are those of both copies; compatibility with their stored rows is not a requirement (decided while specifying), the apps migrate in their own changes.

## Alternatives considered

- **Keep the `core`/`infrastructure` split of `lib--conversations`** (`commons.events.core`, `.infrastructure.sql`, …): mirrors the source, but `commons` has no such layering; its packages put port and adapters side by side.
- **An optional extra for the events** (like `azure`): everything needed (`pydantic`, `sqlmodel`, `sqlalchemy`) is already a dependency; an extra would only add installation steps.
- **One package `commons.events` for both patterns:** live streams have no envelope, outbox or settings in common with it; a separate `commons.streams` keeps each package's guarantees (at least once vs. at most once) clear.
- **Make `UnitOfWorkFactory` a `Protocol` or add `for_current_user`:** would change the existing API for no need of this change; the wrapper works with the API as it is.
- **Each library keeps its own outbox table, `commons` only provides the code:** rejected in the intent: one relay and one set of workers per app.

### Python 3.14

- `pyproject.toml`: `requires-python = ">=3.14, <4.0"`; `poetry lock` refreshed for it.
- `.github/workflows/check.yml`: passes `python-version: "3.14"` to the reusable `python-check.yml` (its default is 3.12).
- `docs/index.md`: "requires Python 3.14 or newer".
- Breaking for every consumer that allows an older Python (`pyhx` `>=3.12`, `app--beleglotse` and `app--cross-border-rules` `>=3.13`): Poetry no longer resolves `commons` for them until they raise their own `requires-python`. Hence `feat!` (R23); release-please derives the next major version from it, so consumers on `versions/0` keep the current release until they move.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Only additions to the public API | R19 for the API; changed while specifying: the move to Python 3.14 is breaking (R22, R23) |
| No new runtime dependency | R19; Design: no extra, `uuid7` from the standard library |
| Built on the existing unit of work, adapted to this `commons`' API | R5, R6, R7, R13; Design: Taking over the code, Wiring |
| Engine-portable SQL with existing column lengths and `UTCDateTime` | R5 |
| Keep guarantees and wire format (envelope, `[app.events]`, file layout) | Guarantees: R10, R16, R17. Changed while specifying: compatibility with data and settings of existing apps is not required; the format is kept as in the source, without a promise |
| `Protocol` ports, no web framework | R6, R9, R11, R16, R18 |
| Behavior kept as tested today | R21 |

## Open questions

None.

## Areas of concern

1. **Covariance of `UnitOfWorkFactory`** (R6, R7): if mypy does not accept an app's `UnitOfWorkFactory[Repositories]` as `UnitOfWorkFactory[HasOutbox]`, every app needs a cast. Handled by a typed test that passes a bundle dataclass to `OutboxRelay` and `background_workers_from_settings` under `poe check`. Owner: Michael Wellner.
2. **Drift while taking over** (R10, R21): the broker's concurrency is subtle; rewriting it invites bugs. Handled by copying the code and its tests (427 lines for the broker alone) unchanged apart from imports and docstrings, and diffing against the source in review. Owner: Michael Wellner.
3. **Migration of `lib--conversations`**: its events are in `conversations_outbox_events`, it depends on the other `commons`, and stored data need not stay readable (decided while specifying); the switch drains the outbox and logs first or starts empty, and aligns the `commons` dependency. Handled in its own change (its T-008). Owner: Michael Wellner.
4. **Migration of `app--beleglotse`**: needs Python 3.14 and the new major version; stored rows and logs need not stay readable (decided while specifying), so it drains them before the switch or starts empty; its handler and stale-run job move to `subscribe` and `maintenance`. Handled in its own change. Owner: Michael Wellner.
5. **Consumers on older Python** (R22, R23): `pyhx`, `app--beleglotse` and `app--cross-border-rules` can't take the new major version before they move to 3.14; they keep `versions/0` until then. The `core--platform` note on Python libraries still names `>=3.12` as the standard. Owner: Michael Wellner.
6. **Table registered on import** (R5): an app that imports `commons.events` but does not use the outbox gets `outbox_events` from `create_all`; same as `commons.storage` and `commons.users` today. Accepted. Owner: Michael Wellner.

## Out of scope

- Several application instances: claiming outbox rows (`SKIP LOCKED`) or leader election, a Kafka or Service Bus broker, a Redis `LiveStreams` (backlog T-010 and T-011 of `lib--conversations`).
- Dead-letter tooling, schema migrations of `outbox_events`.
- The migration of `app--beleglotse` and `lib--conversations`, and aligning `lib--conversations` with this `commons`; each in its own repository.
- Domain events, handlers and processes of the apps and libraries.
- Compatibility with the stored events, file logs and settings of existing apps (decided while specifying).
- `uuid7` for the other ids of `commons` (backlog T-002); updating the Python standard in the `core--platform` note.
