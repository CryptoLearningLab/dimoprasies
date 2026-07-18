# NEXT TASK

Execute:
`Configure email env and enable production timer`

## Current Input

The UI now exposes:

- version badge `v0.1.7`
- SQLite-backed source polling audit
- email alert path `/api/email-alerts`
- SQLite de-duplication through `notification_log`
- CLI scheduled runtime path `tender-radar runtime scheduled-run`
- incremental scheduled AI triage that reuses existing row-key decisions
- systemd templates for `tender-radar-scheduled.service` and
  `tender-radar-scheduled.timer`

The scheduled path runs bounded discovery, AI triage, linked-candidate
enrichment and email alerts. It does not run full-depth/backfill discovery
unless explicitly configured.

Latest droplet dry-runs on `v0.1.7` completed in 4.88s and 4.29s. Discovery,
AI triage and enrichment were all skipped on unchanged state. The timer is
installed but disabled because SMTP/email env keys are missing.

## Instruction

Implement the next small gate:

1. Inspect the droplet `.env.local` keys without printing secret values.
2. Add or confirm required outbound email settings outside chat.
3. Run one controlled email dry-run after env configuration.
4. Run one controlled real-send smoke to the owner address and confirm
   `notification_log` changes only after success.
5. Enable `tender-radar-scheduled.timer` only after email send is verified.

## Required Closeout

1. Run real-send smoke only when env is present.
2. Report `systemctl` timer status and latest audit report path.
3. Confirm the timer is enabled and scheduled with `systemctl list-timers`.
4. Keep all secret values out of logs and docs.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
