# NEXT TASK

Execute:
`Migrate source poller skip state to SQLite`

## Current Input

Runtime state tables now exist in `data/tender_radar.sqlite`:

- `source_state`
- `source_runs`
- `tender_dismissals`
- `notification_log`

The UI "Δεν με ενδιαφέρει" path writes to SQLite and still reads the legacy
`work/derived/ignored_tenders.json` file during migration.

## Instruction

Implement the next small gate:

1. Make the source fingerprint preflight write every source check to
   `source_state` and `source_runs`.
2. Make unchanged-source skip decisions read the previous fingerprint from
   SQLite first, falling back to `work/derived/source_fingerprints.json` only
   for legacy compatibility.
3. Keep bounded search fast; do not introduce full-depth discovery into this
   flow.
4. Preserve existing JSON report outputs until all UI/report consumers are
   migrated.
5. Do not expose or log secrets.

## Required Closeout

1. Run targeted UI/source preflight tests and `.venv/bin/python -m pytest`.
2. Run a local bounded preflight smoke and report whether it skipped or changed.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
