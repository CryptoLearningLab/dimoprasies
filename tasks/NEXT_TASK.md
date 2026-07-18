# NEXT TASK

Execute:
`Email alerts for new active rows`

## Current Input

The first UI screen now shows the live version badge and a SQLite-backed
source polling audit table.

The current source configuration has:

- 31 configured sources
- 25 selective-refresh capable sources
- per-source state in `source_state`
- per-run audit rows in `source_runs`
- email de-duplication table `notification_log`

## Instruction

Implement the next small gate:

1. Build an email alert path that sends only dashboard rows that have not
   already been sent to the recipient.
2. Use SQLite `notification_log` as the canonical de-duplication source.
3. Keep email content clickable: title, authority, budget, deadline, source
   label and official ESHIDIS/source URL.
4. Do not run full-depth discovery as part of email sending; consume the
   already refreshed dashboard state.
5. Do not expose or log secrets.

## Required Closeout

1. Run targeted email/notification tests and `.venv/bin/python -m pytest`.
2. Run a local dry-run smoke that reports how many rows would be emailed and
   how many are skipped as already sent.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
