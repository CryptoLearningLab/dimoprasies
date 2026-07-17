# NEXT TASK

Execute:
`Build discovery watermark and backfill safety`

## Current Input

Use the current discovery flows:

```text
sources discover-active
sources expanded-report
work/reports/eshidis_active_candidates.json
work/reports/expanded_discovery_report.json
```

Latest discovery-depth update as of `2026-07-17`:

```text
ESHIDIS active discovery default limit is 100 rows
KIMDIS expanded report default depth is 20 pages per record family
expanded-report runtime summary.errors are surfaced as warnings/failure in UI
long-running UI actions now run as background jobs polled every 5 seconds
these are safer bounded scans, not a formal no-miss weekly guarantee
```

Recent UI workflow update as of `2026-07-17`:

```text
dashboard row actions now handle per-id Fetch and ZIP document download
KIMDIS fetch supports --official-id for one ADAM at a time
```

## Instruction

Build the next smallest no-miss reliability step:

1. Persist discovery run metadata: started_at, completed_at, source family,
   row/page depth, candidate ids, errors and success/failure.
2. Add a backfill mode that scans until it reaches the previous successful
   run window or a documented source exhaustion condition.
3. Keep bounded demo scans available, but label them as bounded.
4. Surface partial source failures in the UI and reports.
5. Do not promote candidates to `VERIFIED_ACTIVE`; keep status verification
   separate.

Do not store TEE subscription credentials in the repository. Treat TEE as a
future authenticated adapter.

## Required Closeout

At the end of the task:

1. Run the relevant targeted tests and `.venv/bin/python -m pytest` if code
   changed.
2. Update `docs/PROGRESS.md` with exact commands and evidence.
3. Update `docs/DECISIONS.md` only if a real decision was made.
4. Update this file with the next single executable gate.
5. Update `docs/HANDOFF.md` if the project state or next gate changed.
6. Commit and push tracked changes to GitHub unless explicitly told not to.
