# NEXT TASK

Execute:
`Harden authority discovery quality and daily-view prioritization`

## Current Input

Broad authority source coverage is now configured and smoke-tested:

- municipal HTML listings
- WordPress municipal categories
- WordPress page table
- PDE/PSTE regional pages
- Diavgeia API org feeds
- TED API

Latest bounded verification:

```text
authority all-sources smoke: 65 authority candidates, 0 errors
expanded report: 3123 total candidates, 385 focus candidates, 108 authority candidates, 0 errors
dashboard focus payload: 148 total_known, 128 visible, 1 expired_hidden, 2 ignored
```

## Instruction

Improve the quality of the main daily dashboard without reducing recall:

1. Keep every source record in reports/provenance.
2. Add priority flags for authority rows:
   - explicit KIMDIS `26PROC...`
   - explicit ESHIDIS id
   - tender/procurement document links
   - likely tender/procurement title
   - decision/context-only row
3. Show high-priority authority rows in the main dashboard by default.
4. Keep low-priority decision/context rows accessible in reports or a secondary
   view, but do not let them drown the daily active tender workflow.
5. Preserve `Δεν με ενδιαφέρει` skip behavior.
6. Do not mark any authority row `VERIFIED_ACTIVE` without separate official
   status verification.
7. Add tests for priority classification and dashboard filtering.

Do not deduplicate by title only.

## Required Closeout

At the end of the task:

1. Run targeted tests and `.venv/bin/python -m pytest`.
2. Run a bounded live smoke and report source/page counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if the project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
