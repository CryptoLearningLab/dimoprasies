# NEXT TASK

Execute:
`Expose source polling audit in the UI`

## Current Input

The UI version badge shows `v0.1.1`.

Source preflight now writes per-source state to SQLite:

- `source_state`
- `source_runs`

It reads previous fingerprints from SQLite first and uses the legacy
`work/derived/source_fingerprints.json` only as compatibility fallback/output.

## Instruction

Implement the next small gate:

1. Add an API payload for the latest source polling state from SQLite.
2. Show a compact UI section/table with one row per source:
   source id, family/adapter, last status, changed/unchanged, last checked,
   last error and whether it is selective-refresh capable.
3. Make source failures visible without triggering global full-depth discovery
   when unchanged successful sources can still be trusted.
4. Keep bounded search fast; do not introduce full-depth discovery into this
   flow.
5. Do not expose or log secrets.

## Required Closeout

1. Run targeted UI/source polling tests and `.venv/bin/python -m pytest`.
2. Run a local source polling smoke and report per-source counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
