# Changes

Every change of this repository is described here before it is made and kept here after it is done: what is wanted and why (intent), how it is built (spec), and in which steps (plan). Each document is accepted by the developer before the next one is written; code is written only after the plan is accepted. The agent skills of the plugin `core-agent-skills` (core--platform) guide each step.

## Documents

| Document | What it's for | Written by | Gate |
| --- | --- | --- | --- |
| `01--backlog/T-<n>--<slug>.md` | An idea: the problem and a rough outcome, not planned yet | `start-change` | none |
| `T-<n>--<slug>/intent.md` | What is wanted and why: problem, outcome, affected users and systems, constraints | `start-change` | accepted before the spec |
| `T-<n>--<slug>/spec.md` | How: numbered requirements, design, alternatives, open questions, concerns; when closed, the **Outcome** (deviations, findings) | `specify-change`, `close-change` | accepted before the plan |
| `T-<n>--<slug>/plan.md` | In which order: findings, steps with their proof, risks; removed when the change is closed | `plan-change` | accepted before any code |
| `README.md` (this file) | How changes work here, and the prioritized backlog | `setup-change-workflow` | |
| `../CLAUDE.md` | Rules for agents in this repository: the shared section, then the project's own | `setup-change-workflow` | |

## Folders

- `01--backlog/`: ideas, one file each.
- `02--open/`: changes being specified, planned or implemented, one folder each.
- `03--closed/`: done changes (intent and spec with its Outcome), and dropped ideas (a folder each, with the item as `intent.md` and the reason under `## Dropped`).

A change keeps its number `T-<n>` from the backlog to the end; numbers are never reused.

## Backlog

Most important first (reorder by moving lines); items not listed have the lowest priority.

<!-- One line per item: - [T-<n> <Title>](01--backlog/T-<n>--<slug>.md): <a few words>. -->

