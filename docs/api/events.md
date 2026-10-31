# Events

Events with a transactional outbox: an event is stored in the same transaction as the change that caused it, then published and delivered to its handlers in the background, **at least once**. One outbox, one relay and one set of background workers serve an application and the libraries it uses.

## Quickstart

The outbox is one repository of the application's bundle and shares the unit of work with the others. Wire the background workers once and start them with the application:

```python
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine

from commons.database import SqlUnitOfWorkFactory
from commons.events import CommitNotifyingUnitOfWorkFactory, Outbox, SqlOutbox, background_workers_from_settings


@dataclass
class Repositories:  # the app's bundle; anything with an `outbox` works
    invoices: InvoicesRepository
    outbox: Outbox


engine = create_engine("sqlite:///app.db")
SQLModel.metadata.create_all(engine)  # creates `outbox_events` with the app's tables

repositories = CommitNotifyingUnitOfWorkFactory(
    SqlUnitOfWorkFactory(
        sessionmaker(bind=engine, class_=Session),
        lambda session, user: Repositories(invoices=SqlInvoices(session), outbox=SqlOutbox(session)),
    )
)

workers = background_workers_from_settings(repositories)  # reads [app.events]
workers.subscribe(group="invoice-validation", event_type=InvoiceUploaded, handler=validate_invoice)

# In the application's lifespan, e.g. FastAPI:
#   workers.start()  on startup
#   await workers.stop()  on shutdown
```

`CommitNotifyingUnitOfWorkFactory` wakes the relay after every commit, so events are processed right away. Without it, the relay finds new events by polling.

## Concepts

- **Event** (`Event`): an immutable fact that happened, e.g. "an invoice was uploaded". A Pydantic model with a `topic`, an `event_type` and its own fields.
- **Envelope** (`EventEnvelope`): the wire format of an event, routing metadata plus the JSON payload. Outbox and broker only see envelopes.
- **Topic**: the log an event is appended to. Related events share a topic; a library uses topics of its own (e.g. `conversations-runs`).
- **Key**: optional partition key; events with the same key are processed in order, events with different keys in parallel.
- **Outbox** (`Outbox`, `SqlOutbox`): the table `outbox_events` the events are stored in, in the same transaction as the change that caused them. One per application.
- **Relay** (`OutboxRelay`): publishes the stored events to the broker and marks them published.
- **Broker** (`LogBroker` on an `EventLog`): stores the published events per topic and delivers them to the consumers. Kafka or Azure Service Bus could replace it.
- **Consumer group**: a named reader of a topic with its own position (offset). Every group sees every event of the topics it subscribed to.
- **Handler** (`EventHandler`): an async function that processes one typed event. It must be **idempotent**: it may see the same event twice.
- **Dead letter**: an event whose handler kept failing; it is set aside so it cannot block its key.

## Configuration

The background workers are configured under `[app.events]`. All settings are optional; unknown keys are rejected.

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| `mode` | `"file"` \| `"memory"` | `"file"` | `file`: durable topic logs on disk; `memory`: lost on restart, for tests and development. |
| `dir` | path | `<data_dir>/events` | Directory of the `file` broker. |
| `poll_interval_seconds` | float | `5.0` | How often the relay and the consumers look for work they were not woken for. |
| `handler_max_concurrency` | int | `10` | Handlers of one consumer group running at the same time, for events with different keys. |
| `handler_max_attempts` | int | `3` | Attempts of a handler before the event is dead-lettered. |
| `outbox_retention_days` | int | `7` | How long published events are kept in the outbox. |
| `maintenance_interval_seconds` | float | `60.0` | How often the outbox is pruned and the maintenance jobs run. |

```toml
[app.events]
mode = "file"
poll_interval_seconds = 5
handler_max_attempts = 3
```

## Usage

### Define an event

Derive from `Event`, set `topic` and `event_type`, and add the fields the handler needs. Keep events small: reference entities by id. Override `key` if the events of one entity must be processed in order.

```python
from typing import ClassVar

from commons.events import Event


class InvoiceUploaded(Event):
    """An invoice was uploaded and waits to be validated."""

    topic: ClassVar[str] = "invoices"
    event_type: ClassVar[str] = "invoice_uploaded"

    invoice_id: str
    customer_id: str

    @property
    def key(self) -> str:
        """The invoices of one customer are validated in the order they were uploaded."""
        return self.customer_id
```

- Name events in the past tense or as a request that happened (`InvoiceUploaded`, `RunRequested`), not as commands.
- `event_type` must be unique within its topic and never change: it is stored in the outbox and the broker.
- Add optional fields only; never rename or remove one. For an incompatible change, define a new event type.

### Publish an event

Add the event to the outbox in the same unit of work as the change. Never publish to the broker directly.

```python
async def upload_invoice(repositories, customer_id: str, data: bytes) -> str:
    with repositories.for_system() as (repos, commit):
        invoice = repos.invoices.add(customer_id, data)
        repos.outbox.add_event(InvoiceUploaded(invoice_id=invoice.id, customer_id=customer_id))
        await commit()  # stores invoice and event together; wakes the relay

    return invoice.id
```

If the unit of work is rolled back, neither the invoice nor the event is stored.

### Handle an event

A handler is an async function that takes the typed event. Subscribe it with a consumer group before starting the workers. Raising makes the consumer retry the event; after `handler_max_attempts` it is dead-lettered.

```python
async def validate_invoice(event: InvoiceUploaded) -> None:
    invoice = ...  # load the invoice by event.invoice_id
    if invoice is None or invoice.status != "uploaded":
        return  # redelivered or outdated event: nothing to do

    ...  # validate it, store the outcome


workers.subscribe(group="invoice-validation", event_type=InvoiceUploaded, handler=validate_invoice)
```

- **Be idempotent.** Check the state before acting, or use `event.event_id` to detect duplicates.
- **Load current state.** The event says what happened; the database says what is true now.
- **Raise only for transient errors** that a retry can fix (e.g. a network error). Record business failures in the domain state and return normally.
- **One handler per event type and group.** Use separate groups for independent reactions to the same event.
- **Persist long work step by step**, each step in its own short unit of work, so no transaction stays open during slow calls; chain steps with further events.

### Libraries

A library adds its events to the application's outbox: its repository bundle gets the `outbox` from the application's session (e.g. `SqlOutbox(session)`), and it offers a function that subscribes its handlers, e.g. `subscribe_processes(workers, registry)`. The application calls it before starting the workers.

### Add maintenance jobs

Periodic jobs, e.g. failing work left behind by a crash, run at start and every `maintenance_interval_seconds`, after the outbox is pruned:

```python
workers = background_workers_from_settings(repositories, maintenance=[fail_stale_runs])
```

### Test asynchronous code

- Use `EventsSettings(mode="memory")` for the workers and SQLite in memory for the outbox.
- Test handlers directly by calling them with an event; they are plain async functions.
- Test that a domain function adds the event: read `repos.outbox.list_unpublished(...)` after it ran.
- For end-to-end tests, start the workers, call the domain function and wait until the handler's effect is visible.

## Behavior

- **At least once.** Every committed event is delivered to every subscribed group at least once; after a crash it may be delivered again.
- **Order per key.** Within a topic, a group processes the events of one key one after the other, in the order they were committed. Events with different keys, and events without a key, are processed in parallel, at most `handler_max_concurrency` at a time.
- **Redelivery after a crash.** The committed offset only moves past events that are all processed: every unfinished event is delivered again, and so are finished events after an unfinished one.
- **A failing event only holds up its own key**, until it is dead-lettered after `handler_max_attempts`. Unreadable events (the payload no longer validates) are dead-lettered right away.
- **Events nobody subscribed to are skipped**; a group subscribed later does not see them.
- **Processing starts after the commit.** Within the domain function the work is not done yet; return the pending state to the caller.
- **Crashed tasks restart.** A background task that crashes is logged and restarted; `stop` never waits longer than its timeout.
- **Single application instance.** The relay and `LogBroker` assume one running instance; several would publish events twice.

## Errors

| Exception | Raised when | What to do |
| --- | --- | --- |
| `ValueError` | `subscribe` is called twice for the same group and event type. | Use one handler per event type and group, or a second group. |
| `RuntimeError` | `BackgroundWorkers.subscribe` is called after `start`, or `start` is called twice. | Subscribe all handlers before starting the workers. |
| `ValueError` | `Event.from_envelope` gets an envelope of another type, or one whose payload doesn't validate. | Only happens when converting envelopes by hand. |
| `ValueError` | `FileEventLog` gets a topic or group name that is not a safe file name. | Use letters, digits, `.`, `_` and `-`. |
| `ValidationError` | `[app.events]` has an unknown key or an invalid value. | Fix the settings. |

## API reference

::: commons.events
