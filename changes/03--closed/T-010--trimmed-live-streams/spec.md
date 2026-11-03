# T-010 Trimmed live streams: spec

## Requirements

- **R1** `InMemoryLiveStreams(max_length=N)` keeps at most the last `N` payloads of each stream; an append that exceeds it drops the oldest ones.
- **R2** Positions don't change by trimming: the n-th payload ever appended to a stream has position `"n"`.
- **R3** A reader without `after`, or with an `after` before the oldest kept payload, gets the kept payloads from the oldest on, then the new ones live; a reader with a later `after` behaves as today.
- **R4** `max_length` must be at least 1 (`ValueError` otherwise); `None` (default) keeps every payload as today.
- **R5** The docs (`docs/api/streams.md`) describe `max_length` and when to use it (streams that are never closed).

## Design

`_Stream` gets `dropped: int` (payloads removed from the front). `append` extends `payloads`, then, with `max_length`, removes the excess from the front and adds it to `dropped`. `read` keeps its absolute position: it yields `payloads[position - dropped]` while `position < dropped + len(payloads)`, and moves `position` up to `dropped` first if it is behind. The `LiveStreams` protocol is unchanged: trimming is a property of the backend's configuration, as retention is.

## Alternatives considered

- **`max_length` per `append`** (as Redis' `XADD MAXLEN`): changes the protocol for every backend and lets writers of one stream disagree; a backend setting is enough for the known use.
- **Expiring idle open streams:** bounds the number of streams, not their length; not needed yet.

## Constraint mapping

| Constraint (intent) | Met by |
| --- | --- |
| Non-breaking | R4 (default `None`) |
| Semantics a shared store can offer | R2, R3 (as Redis stream ids and `XREAD`) |

## Open questions

None.

## Areas of concern

1. **Readers that fall behind miss payloads** (R3): intended (at most once); documented. Owner: this change.

## Out of scope

- A Redis adapter, idle expiry (intent).

## Outcome

Implemented as specified, with this finding (from the plan, removed at close-out):

- **F1** The first version moved a reader to the oldest kept payload only before its loop; a reader waiting at its `yield` while the stream was trimmed then read a wrong index. The check now runs for every payload (test `test_a_live_reader_that_falls_behind_continues_after_the_trimmed_part`).

Rollout: released with the next Release PR (1.7.0), first used by app--casesight T-020.

Open after this change: nothing.
