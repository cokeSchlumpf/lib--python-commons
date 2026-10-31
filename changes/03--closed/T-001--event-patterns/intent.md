# T-001 Event patterns: transactional outbox and live streams

## Problem

Two event patterns are implemented, almost line by line, in more than one place, and every new app or library copies them again:

- **Transactional outbox with at-least-once delivery**: `Event`/`EventEnvelope`, the outbox port and its SQL table, `OutboxRelay`, the in-process `LogBroker` on an `EventLog` (file or memory), `CommitNotifyingUnitOfWorkFactory`, `BackgroundWorkers` and `EventsSettings` (`[app.events]`). It exists in `app--beleglotse` (`_01_domain/events`, `_01_domain/ports`, `_02_infrastructure/background`, `adapters/messaging`, `adapters/sql/outbox_repository`) and in `lib--conversations` (`core/events`, `core/ports`, `infrastructure/background`, `infrastructure/messaging`, `infrastructure/sql/_outbox*`). The copies have already drifted: `lib--conversations` has per-key parallelism in the broker, `subscribe` and maintenance jobs on the workers, and `Protocol` ports; `app--beleglotse` still hard-wires its handler and its stale-run job into `BackgroundWorkers` and uses ABC ports.
- **Short-lived live streams with at-most-once delivery**: `LiveStreams` (append, close, read from a position, fan-out to every current reader, not durable, retention after close), `InMemoryLiveStreams`, and the typed view `TypedLiveStreams` with `Codec`/`PydanticCodec`. It exists only in `lib--conversations` (run streams), but is generic: an app can use it for its own live views, e.g. the progress of a job.

Because the outbox lives in each package, an app that uses `lib--conversations` runs two outboxes, two relays and two sets of background workers (`conversations_outbox_events` next to the app's `outbox_events`). Fixes and features (e.g. multi-instance support, dead-letter tooling, a Redis adapter for live streams) would have to be made in every copy. `lib--conversations` already has this as backlog item T-008 "Move outbox, relay and workers to commons".

## Proposed outcome

- Both patterns are delivered in this one change, as two packages: `commons.events` and `commons.streams`; the existing `src/jobs` package stays separate (a job runner, not an event pattern).
- `commons.events` offers the outbox pattern: the event model, the ports (outbox, publisher, consumer/subscriber), the SQL outbox table and adapter, the relay, the in-process broker with its file and in-memory logs, the commit-notifying unit of work, the background workers and their settings under `[app.events]`, with the behavior of the current `lib--conversations` version (GitHub `main`) as the reference: `Protocol` ports, `subscribe` and maintenance jobs on the workers, order per key with parallel keys, at least once, retries, dead letters, pruning, single instance; the differences of `app--beleglotse` (hard-wired handler and job, ABC ports, `extra="ignore"` in the settings) are not taken over.
- `commons.streams` offers the live-stream pattern: the `LiveStreams` port, the in-memory adapter, and the typed view with its codecs, with the behavior of the current `lib--conversations` version (at most once, fan-out, resumable by position, retention after close, single instance).
- An app and the libraries it uses share one outbox, one relay and one set of background workers, and one live-streams backend; the app wires them once. `commons` defines the one outbox table (`outbox_events`), the app creates it, and libraries add their events to the app's outbox through its unit of work, on their own topics (e.g. `conversations-runs`); the relay only needs a repository bundle that has an `outbox`.
- `app--beleglotse` and `lib--conversations` can replace their copies by the `commons` packages; the migration of both is done in their own repositories, as their own changes, not in this one.
- Documented in the mkdocs site (concepts, usage, configuration, behavior), as in the T-016 and T-018 specs of `lib--conversations`.
- Not part of this change: several application instances (relay with `SKIP LOCKED` or leader election, a Kafka/Service Bus broker, a Redis live-streams adapter), dead-letter tooling, schema migrations of the outbox table, and the domain events, handlers and processes of the apps.

## Affected users and systems

- **`lib--python-commons`:** new public API (an addition, `feat`, minor version); `pydantic` becomes a direct use (already present via `sqlmodel`).
- **`lib--conversations`:** later drops its copy and its own outbox table, and subscribes its handlers on the app's workers; its public API (`conversations.core.events`, `conversations.infrastructure.background`, `.messaging`) changes there. It is built on another, almost identical `commons` (`lib--commons@versions/1` on Azure DevOps) with minor differences, e.g. `UnitOfWorkFactory.for_current_user()`, which its `CommitNotifyingUnitOfWorkFactory` uses and this `commons` lacks; using `commons.events` means aligning or switching that dependency there.
- **`app--beleglotse`:** later drops its copy; its stored outbox rows and file logs must stay readable or be drained before the switch.
- **Other apps using `commons`** (e.g. cross-border-rules): can use the patterns instead of building their own.
- **Existing `commons` users:** unaffected; nothing existing changes.

## Constraints

- Only additions to the public API; nothing existing in `commons` changes (`versions/0` consumers).
- No new runtime dependency: standard library, `pydantic`/`sqlmodel`/`sqlalchemy` and `commons` itself (`database`, `settings`, `users`, `datetime_operators`) only.
- Built on the existing unit of work of `commons.database` (`UnitOfWork`, `UnitOfWorkFactory`, `SqlUnitOfWorkFactory` with an app-defined repositories factory): the outbox is one repository in the app's bundle and shares its transaction; no second persistence abstraction. Code taken from `lib--conversations` is adapted to this `commons`' API (`for_user`, `for_system`, entering the factory).
- Engine-portable SQL (SQLite for tests, SQL Server / Azure SQL in production), using the existing column lengths and `UTCDateTime`.
- Keep the guarantees and the wire format of the existing copies (envelope fields, `[app.events]` keys and defaults, file log layout), so both consumers can switch without losing stored events.
- Ports are `Protocol`s and the core is free of any web framework, like the rest of `commons`.
- Behavior kept as tested today: the tests of both copies move along with the code.

## Open questions

None.
