# NEXT TASK

Execute:
`Six-hour scheduled poll and alert`

## Current Input

The UI now exposes:

- version badge `v0.1.2`
- SQLite-backed source polling audit
- email alert path `/api/email-alerts`
- SQLite de-duplication through `notification_log`

Email sending consumes the existing dashboard state only. It does not run
discovery, document fetching, OCR or AI classification.

## Instruction

Implement the next small gate:

1. Add a scheduled runtime entry point for the droplet that can run every 6
   hours.
2. The scheduled job should perform the bounded daily sequence only:
   source preflight/discovery when needed, AI triage/enrichment, then email
   alerts.
3. Do not run full-depth/backfill discovery unless explicitly configured.
4. Persist a readable run/audit artifact with source counts, skipped sources,
   changed sources, email new/skipped counts and errors.
5. Keep the UI path and scheduler path sharing the same core helpers where
   practical.
6. Do not expose or log secrets.

## Required Closeout

1. Run targeted scheduler/email tests and `.venv/bin/python -m pytest`.
2. Run a local dry-run scheduler smoke.
3. Deploy to the droplet and run a droplet-side dry-run smoke through `ssh`,
   not through a temporary tunnel.
4. Update `docs/PROGRESS.md`.
5. Update `docs/DECISIONS.md` only if a real decision was made.
6. Update this file with the next single executable gate.
7. Update `docs/HANDOFF.md` if project state or next gate changed.
8. Commit and push tracked changes to GitHub unless explicitly told not to.
