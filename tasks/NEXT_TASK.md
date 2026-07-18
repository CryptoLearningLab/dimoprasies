# NEXT TASK

Execute:
`Expose unresolved linked ESHIDIS attempts in the UI`

## Current Input

The UI discovery pipeline now performs canonical linked-ESHIDIS enrichment:

- source preflight can skip unchanged sources before expensive discovery,
- selective refresh runs only changed delta-capable sources,
- KIMDIS/authority rows pass a deterministic public-works gate,
- non-ESHIDIS documents/source text can produce `linked_eshidis_ids`,
- missing linked ids are fetched through the official ESHIDIS detail and
  attachment commands,
- KIMDIS/authority duplicates are hidden only after the linked id appears as a
  real canonical ESHIDIS dashboard row,
- failed unresolved linked ids are logged in
  `work/derived/linked_eshidis_fetch_attempts.json` and skipped on later
  bounded searches.

Current smoke found one unresolved linked id:

- `221365`: `sources fetch-resource` succeeded, but
  `sources download-attachment --all` failed with `No attachment rows
  selected.`

## Instruction

Implement a small UI/status gate for unresolved linked ESHIDIS attempts:

1. Show unresolved linked ESHIDIS attempt status on candidate previews and/or
   row pills without hiding the source candidate.
2. Add a clear manual retry path for a single unresolved linked ESHIDIS id.
3. Keep the bounded search fast by preserving the attempt ledger skip behavior.
4. Do not mark unresolved ids as `VERIFIED_ACTIVE`.
5. Preserve raw KIMDIS/authority provenance and do not dedupe by title.

## Required Closeout

At the end of the task:

1. Run targeted UI tests and `.venv/bin/python -m pytest`.
2. Run a bounded local smoke and report attempted/enriched/failed/skipped
   counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
