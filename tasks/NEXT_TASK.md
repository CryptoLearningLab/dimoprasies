# NEXT TASK

Execute:
`Add scheduled discovery and new-candidate notification wiring`

## Current Input

Use the current discovery flows and runtime watermark file:

```text
sources discover-active
sources expanded-report
work/reports/eshidis_active_candidates.json
work/reports/expanded_discovery_report.json
work/derived/discovery_runs.json
```

Latest reliability update as of `2026-07-18`:

```text
bounded discovery remains available for quick/manual runs
backfill safety mode persists discovery run metadata
backfill increases ESHIDIS/KIMDIS depth until previous successful run window is reached or max depth is hit
KIMDIS expanded report includes source_pages metadata for page-level exhaustion evidence
discovery runs remain candidate-only and never emit VERIFIED_ACTIVE
KIMDIS linked ESHIDIS extraction handles dotted Ε.Σ.Η.ΔΗ.Σ Α/Α labels
KIMDIS previews expose already-downloaded linked ESHIDIS file counts
KIMDIS linked ESHIDIS extraction handles official resources/search/<id> URLs
KIMDIS linked ESHIDIS extraction handles guarded Α/Α Διαγωνισμού labels
```

## Instruction

Build the next smallest daily-ops step:

1. Add a scheduled discovery entry point suitable for cron/container use.
2. Compare the latest run against the latest previous successful watermark.
3. Produce a new-candidates report with source id, title, authority, deadline,
   source URL and reason.
4. Keep email sending or other notifications explicit/configurable; do not
   hardcode recipient addresses.
5. Surface partial source failures in the generated report.
6. Do not promote candidates to `VERIFIED_ACTIVE`; keep status verification
   separate.

Do not store TEE subscription credentials or email secrets in the repository.

## Required Closeout

At the end of the task:

1. Run the relevant targeted tests and `.venv/bin/python -m pytest` if code
   changed.
2. Update `docs/PROGRESS.md` with exact commands and evidence.
3. Update `docs/DECISIONS.md` only if a real decision was made.
4. Update this file with the next single executable gate.
5. Update `docs/HANDOFF.md` if the project state or next gate changed.
6. Commit and push tracked changes to GitHub unless explicitly told not to.
