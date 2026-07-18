# NEXT TASK

Execute:
`Expose AI triage and candidate enrichment status in the UI`

## Current Input

The UI bounded discovery flow now chains:

1. bounded/selective discovery,
2. OpenAI-backed `sources ai-triage-report` through `/api/ai-triage`,
3. non-ESHIDIS candidate enrichment through `/api/enrich-candidates`.

The AI report is written to `work/reports/ai_triage_report.json` and the
candidate enrichment ledger is written to
`work/derived/candidate_enrichment_attempts.json`.

## Instruction

Implement a small UI/status gate:

1. Show whether the latest visible rows are filtered by a fresh AI triage
   report or an older cached report.
2. Show candidate enrichment summary: attempted, enriched, failed and skipped.
3. Add a manual retry path for one row that clears only that row's enrichment
   attempt and reruns fetch/enrichment.
4. Keep bounded search fast; do not introduce full-depth discovery into this
   flow.
5. Do not expose or log the OpenAI API key.

## Required Closeout

1. Run targeted UI tests and `.venv/bin/python -m pytest`.
2. Run a bounded local smoke and report AI/enrichment status.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
