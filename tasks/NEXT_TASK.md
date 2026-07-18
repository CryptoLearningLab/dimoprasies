# NEXT TASK

Execute:
`Integrate advisory triage into the daily dashboard`

## Current Input

Broad source discovery now produces many correct raw records, but the daily UI
is too noisy for contractor workflow.

Latest AI triage dry run over the current focus dashboard:

```text
dashboard input: 148 total_known, 128 visible, 1 expired_hidden, 2 ignored
AI triage rows: 128
KEEP_ACTIVE_TENDER: 17
REVIEW_TENDER_CANDIDATE: 18
EARLY_SIGNAL: 4
DROP_OUT_OF_SCOPE_SUPPLY_SERVICE: 39
DROP_ADMIN: 47
DROP_NOT_PUBLIC_WORKS: 3
kept/review/early total: 39
dropped total: 89
errors: 0
```

Reports:

- `work/reports/ai_triage_report.json`
- `work/reports/ai_triage_report.md`

## Instruction

Improve the daily dashboard without reducing recall:

1. Load cached AI triage results from `work/reports/ai_triage_report.json`
   when present.
2. Show `KEEP_ACTIVE_TENDER` and `REVIEW_TENDER_CANDIDATE` rows in the main
   daily view by default.
3. Decide whether `EARLY_SIGNAL` rows appear by default or behind a toggle.
4. Hide `DROP_*` rows by default but keep them accessible through a secondary
   view/toggle and reports.
5. Preserve `Δεν με ενδιαφέρει` skip behavior.
6. Do not delete source records, mutate provenance, deduplicate by title, or
   promote anything to `VERIFIED_ACTIVE`.
7. Add tests for cached triage loading and dashboard filtering/toggles.

## Required Closeout

At the end of the task:

1. Run targeted tests and `.venv/bin/python -m pytest`.
2. Run a dashboard smoke and report visible/hidden counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
