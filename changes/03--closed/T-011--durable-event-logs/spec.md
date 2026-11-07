# T-011 Event logs in durable storage: spec

## Requirements

### Both logs

- **R1** `[app.events] mode` also takes `"sql"` and `"azure_blob"`; `background_workers_from_settings` builds `SqlEventLog` or `AzureBlobEventLog`. `"file"` stays the default, and existing settings keep working.
- **R2** Both implement `EventLog`: an event read comes with the offset after it, and reading from that offset continues behind it. Topics, offsets and dead letters survive a new instance of the log.
- **R3** A consumer that committed an offset never misses an event appended before it became visible at that offset, also with two writers at the same time: per topic, the order of offsets is the order in which events become visible.
- **R4** Each log creates what it needs when it is built: tables or container, without error if they exist.

### `sql`

- **R5** `SqlEventLog` uses an engine of its own, with its own connection pool (`[app.events.sql] pool_size`, default 2), and one transaction per call. It takes the connection from `[app.database]`, and its tables aren't in `SQLModel.metadata`, so an app's `create_all` doesn't create them in apps that don't use it.
- **R6** It works on SQLite and SQL Server, without dialect-specific SQL.

### `azure_blob`

- **R7** `AzureBlobEventLog` stores in a container of its own (`[app.events.azure_blob] container`, default `events`), in the account of `[app.storage.azure]`.
- **R8** A topic isn't limited by the 50,000 blocks of an append blob: it continues in another blob, without a consumer missing an event, also if a second writer still appends to the old one.

### Broker

- **R9** `LogBroker` calls its log outside the event loop, every method of it. Commits of one subscription stay in order.
- **R10** The existing behaviour of `LogBroker` with `file` and `memory` doesn't change.

### Documentation

- **R11** `docs/api/events.md` describes the modes, their settings and what they guarantee. Types are exported from `commons.events`.

## Design

**Broker.** `publish`, the reader, `dead_letter` and `committed_offset` go through `asyncio.to_thread`. `_Consumption` gets the committed offset as an argument, read before it is built. `_commit` becomes async and holds an `asyncio.Lock`: otherwise two threads could store offsets in the wrong order, and an older one would win. A cancelled commit may still reach the log, which only means less redelivery.

**`SqlEventLog(engine)`** in `events/sql_log.py`. Own registry (`class _Model(SQLModel, registry=registry())`), so `SQLModel.metadata` stays as it is:

```text
event_log_topics      topic (PK), last_sequence
event_log_entries     topic + sequence (PK), envelope (text)
event_log_offsets     consumer_group + topic (PK), position
event_log_dead_letters  id (PK), consumer_group, topic, envelope, error, dead_lettered_at
```

`append` is one transaction: `UPDATE event_log_topics SET last_sequence = last_sequence + 1 WHERE topic = …`, read the value, insert the entry, commit. The update holds the row's lock until the commit (the whole database's on SQLite), so a second writer waits, and sequences of a topic become visible in order and without gaps. A missing topic row is inserted first, ignoring the `IntegrityError` of a writer that was faster. The offset is the entry's sequence; `0` is the start.

`read` selects `sequence > offset` in order, `commit_offset` updates and inserts if no row changed (again ignoring the `IntegrityError` of a concurrent insert, then updating). The envelope is stored as JSON text (`UnicodeText`), as nothing queries it.

`create_engine()` of `commons.database_operators` gets optional `pool_size` and `pool_pre_ping`, used only by this log: a dropped connection should not fail a consumer. Its defaults leave today's engines unchanged.

**`AzureBlobEventLog(container_client)`** in `events/azure_blob.py`, same layout as `FileEventLog`, with append blobs:

```text
topics/<topic>/<segment, 10 digits>.jsonl
_offsets/<group>/<topic>.json
_dead_letters/<group>/<topic>.jsonl
```

The offset is `segment << 40 | position in the segment's bytes`, so it stays an opaque integer. `append` appends one block per line (atomic, so no partial lines), to the topic's current segment. When the block count returned reaches `max_blocks` (default 49,000), the writer seals the blob and moves on. A blob that answers `BlobIsSealed`, because another writer sealed it, makes the writer move to the next segment and append there.

`read` looks at the segment's properties; only if the position is at its end and the blob is **sealed** does it go on to the next segment. As a sealed blob can't grow, no event can appear behind a reader that moved on. That's what R8 asks for, and why sealing is needed rather than just starting a new blob.

**Settings.** `EventsSettings` gets `sql: SqlEventLogSettings` and `azure_blob: AzureBlobEventLogSettings`, each with its default. `_build_container_client` in `commons.storage.azure` gets an optional container name.

## Alternatives considered

- **`IDENTITY` as the offset in `sql`:** a later id can become visible before an earlier one commits (R3).
- **Sharing the app's engine:** a slow log could use up the domain's connections, which the developer ruled out.
- **`SQLModel.metadata` for the tables:** every app's `create_all` would create empty tables.
- **Block blobs rewritten at every append, or one blob per event:** slow, or very many blobs, and listing them gets slower with each.
- **Starting a new blob without sealing:** a second writer could still append to the old one behind a reader's back (R8).

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| At least once | R2, unchanged broker logic (R10) |
| Azure's packages in the extra, none for `sql` | Imports as in `commons.storage.azure`; SQLModel is there |
| The domain's transactions and pool untouched | R5 |
| SQLite and SQL Server | R6, no dialect-specific SQL |
| Reliable order | R3, R8 |
| Two containers during a deployment | R3, R8; a second consumer means redelivery, which at least once allows |

## Open questions

None. The developer left the decisions of this spec to the author up to the final pull request.

## Areas of concern

1. **SQL Server isn't tested here** (R6): this machine has no container runtime yet. The tests run on SQLite; `create_all` for `mssql` can only be compiled. App--casesight's T-031 runs against SQL Server in a container, and is the first real run. Owner: author.
2. **The real Azure account isn't tested** (R8): the tests use a fake container and one run against Azurite. Sealing depends on the service's API version. Owner: author.
3. **Thread pool** (R9): `to_thread` shares the default pool with handlers (5 threads on one core). A log call waits while handlers fill it, which slows events, not requests. Owner: author.
4. **Unbounded growth** (intent): the logs keep every event. Small events, but a retention is a follow-up. Owner: developer.

## Out of scope

- Retention of events, and a distributed consumer: two containers in overlap each deliver, as the broker stays in-process.
- Event Hubs or other brokers.
- Changes to the outbox.

## Outcome

Implemented as specified, with these deviations and findings (from the plan, removed at close-out):

- **F1** The relay reads the outbox, closes that transaction, publishes, and marks in a new one, so the log is never inside a domain transaction.
- **F2** An `UPDATE` that changes no row still holds a transaction open: creating a topic's row from a second session then waits for itself, which the tests found on SQLite. `append` ends the first transaction before it.
- **F3** The offset of `test_after_a_restart_unfinished_events_are_delivered_again` was checked at the moment the handler ended; the commit now follows in another thread, so the test waits for it. The guarantee is the same: a commit cancelled at shutdown means redelivery.
- **F4** Against Azurite with the real SDK: sealing, the seal's refusal (`ResourceExistsError` with `error_code` `BlobIsSealed`), segments, offsets across them and delivery through the broker work.

Checked: `poe check` (722 passed), `mkdocs build --strict`, the run against Azurite. Broker tests run on all four logs.

Not checked: `SqlEventLog` against a real SQL Server, only on SQLite and as compiled DDL (R6); `AzureBlobEventLog` against a real storage account. App--casesight's T-031 runs against SQL Server in a container, and should do so before this is released.

Rollout: a minor release of `versions/1`, after the developer's review. Nothing changes for apps until they choose a mode.

Open after this change: the first real run on SQL Server (T-031 of app--casesight, author); a retention for the logs, as they keep growing (developer).
