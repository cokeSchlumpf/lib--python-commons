# T-010 Trimmed live streams

## Problem

`InMemoryLiveStreams` keeps every payload of a stream until the stream is closed (and then for `retention` seconds). That suits a stream per job, which ends with the job. An app that wants one live stream per long-lived thing (e.g. the changes of a case, which never "ends") can't use it without its memory growing for as long as the process runs, or without inventing rolling keys that writer and reader must agree on.

## Proposed outcome

- A live stream can be kept to its last N payloads: `InMemoryLiveStreams(max_length=N)` drops older payloads on append. Positions keep counting, so a payload keeps its position; a reader that resumes before the oldest kept payload continues with it (it misses the dropped ones, as at-most-once delivery allows).
- Without `max_length` nothing changes.
- Deliberately not part of it: idle expiry of open streams, a Redis adapter.

## Affected users and systems

- **Apps using `commons.streams`:** may pass `max_length`; nothing changes otherwise. First user: app--casesight T-020 (one stream per case).

## Constraints

- Non-breaking (a keyword with the current behaviour as default), released as a minor version on `versions/1`.
- Semantics a shared-store adapter can offer too (Redis `XADD MAXLEN`, `XREAD` after a trimmed id).

## Open questions

None.
