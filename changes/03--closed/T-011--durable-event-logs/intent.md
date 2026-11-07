# T-011 Event logs in durable storage

## Problem

`create_background_workers` offers two event logs: `file` (topic logs below `<data_dir>/events`) and `memory`. In a container without persistent storage, both are lost at every restart. The outbox then counts the events it relayed as published and never resends them, so an event that wasn't processed yet is gone. App--casesight is about to move to a database on UAT (its T-031), where exactly this happens: an uploaded file's page images would stay `pending` for good, while the rest of the data survives.

Apps that keep their data in Azure have nowhere durable to put their events, and each one would have to find its own way around it.

## Proposed outcome

- Two more event logs next to `file` and `memory`, chosen by `[app.events] mode`, both implementing the existing `EventLog` protocol (`append`, `read`, `committed_offset`, `commit_offset`, `dead_letter`):
  - `sql`: `SqlEventLog`, in the app's database, with **its own engine and connection pool** and a transaction of its own for each call. It never takes part in a domain transaction, which is also how the relay works today: it reads the outbox, closes that transaction, publishes, and marks the events in a new one.
  - `azure_blob`: `AzureBlobEventLog`, in a storage account, in a container of its own (not the one of `Files`), with the settings of `[app.storage.azure]` for the account. The name leaves room for other Azure services later, such as Event Hubs.
- Topics, offsets and dead letters survive a restart in both.
- Each log creates what it needs at startup, like `Files` and `create_all` do elsewhere: `create_all` for its own tables, `create_if_not_exists` for the container (the account key allows it). Apps need no Terraform for it and only choose the mode.
- Little to configure: `[app.events.azure_blob] container` (default `events`) and `[app.events.sql] pool_size` (a small default such as 2). `sql` uses the settings of `[app.database]`, `azure_blob` those of `[app.storage.azure]`. Nothing else until someone needs it.
- The broker doesn't block the event loop: `LogBroker` calls its log directly (`self._log.append(…)`), which is fine for a local file but holds up every other request over a network.
- Existing apps don't change: `file` stays the default, and neither the protocol nor the settings of today change in a breaking way. Released as a minor version of `versions/1`.
- It deliberately adds no retention: logs keep growing, as `file` does today.

## Affected users and systems

- **App--casesight:** sets the mode on UAT in its T-031; it's the first user.
- **Other apps using the background workers (`app--beleglotse`):** see no change, unless they choose a new mode.
- **`LogBroker` and all its users:** calling the log outside the event loop changes where the code runs, not what it does; the existing logs must keep working with it.

## Constraints

- Delivery stays at least once. A crash between publishing and marking in the outbox may publish an event again, and handlers must already cope with that.
- Azure's packages stay in the extra `azure` of `commons`, and `sql` needs no new dependency.
- The domain's transactions and pool aren't touched, so that a slow or broken event log can't exhaust them, and a domain rollback can't take a published event with it.
- Works on SQLite and on SQL Server, as apps use both (`NVARCHAR` for text, no dialect-specific SQL).
- Each log must keep events in an order consumers can rely on: a consumer that committed an offset must never miss an event written before it.
- `FileEventLog` is documented as single process. During a deployment, old and new containers can share a durable log for a moment; the new logs must stay correct then.

## Known risks, for the spec

- **Offsets in `sql`:** an auto-incremented id isn't safe as an offset with two writers: a later id can become visible before an earlier one commits, and a consumer that read past it would miss that event. It matters only while two containers overlap, but the constraint above asks for it to hold.
- **Limit of append blobs in `azure_blob`:** from memory, an append blob takes at most 50,000 blocks, so a topic of one blob would stop accepting events at about 50,000. Not checked against the documentation. It would fail hard, so the log needs segments or another way around it, within the opaque integer offset of the protocol.
- **Polling costs:** consumers look for work every `poll_interval_seconds` per group and topic, which is several requests a minute to the storage account or the database. Not measured.

## Open questions

None.
