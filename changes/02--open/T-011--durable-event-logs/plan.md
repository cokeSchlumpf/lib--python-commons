# T-011 Event logs in durable storage: plan

## Findings while planning

- **F1** The relay reads the outbox, closes that transaction, publishes, and marks in a new one, so the log is never inside a domain transaction.
- **F2** `seal_append_blob` and `is_append_blob_sealed` exist in the installed SDK; `append_block` returns `blob_committed_block_count`.
- **F3** `test_storage_azure.py` tests with mocks; the new log needs a fake with append semantics, or the contract can't be tested.

Deviations from the spec:

- None.

## Branching

Branch `feature/durable-event-logs`, draft pull request #47. The developer waived the review after each step, up to the final pull request, which they review before merging.

## Steps

### 1. The broker off the event loop

- `to_thread` for every call of the log, a lock around commits. **R9, R10**
- Proof: the existing broker tests unchanged; a new test that no log method runs on the event loop's thread and commits arrive in order.

### 2. `SqlEventLog`

- `events/sql_log.py`, options of `create_engine`. **R2, R3, R4, R5, R6**
- Proof: a contract test for all logs (`memory`, `file`, `sql`, then `azure_blob`); two threads appending on a SQLite file give gap-free sequences read in order; `SQLModel.metadata` has no new tables; the tables compile for `mssql`.

### 3. `AzureBlobEventLog`

- `events/azure_blob.py`, the container name in `_build_container_client`. **R2, R3, R4, R7, R8**
- Proof: the contract test with a fake container; rolling over with a small `max_blocks`; a second writer on a sealed blob; a reader that doesn't move on before the seal. One run against Azurite.

### 4. Settings and documentation

- `EventsSettings`, `background_workers_from_settings`, exports, `docs/api/events.md`. **R1, R11**
- Proof: `poe check`; `mkdocs build --strict` if it can run; a run of the background workers with each mode.

## Risks

- **`to_thread` changes timing in tests:** run the existing tests first; if one depends on the order within a tick, the test or the design is reconsidered, and recorded here.
- **Azurite may not support sealing:** then the fake is the proof, and that's reported in the pull request.

## Proof per requirement

| Requirement | Proven by |
| --- | --- |
| R1 | Step 4, settings test and workers run |
| R2 | Steps 2, 3, contract test |
| R3 | Step 2, concurrent test; step 3, seal tests |
| R4 | Steps 2, 3, building a log twice |
| R5 | Step 2, tests of the engine and metadata |
| R6 | Step 2, SQLite and compiled DDL; first real run in app--casesight's T-031 |
| R7 | Step 3, settings test |
| R8 | Step 3, roll-over tests |
| R9 | Step 1 |
| R10 | Step 1, existing tests |
| R11 | Step 4, `mkdocs build --strict` |
