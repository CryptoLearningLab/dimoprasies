# NEXT TASK

Execute:
`Stabilize ESHIDIS scheduler skip and enable production timer`

## Current Input

The UI now exposes:

- version badge `v0.1.5`
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

Latest droplet dry-run on `v0.1.4` completed in about 33 seconds with AI triage
skipped. The remaining avoidable delay is `eshidis_active_search` changing
often enough to trigger bounded ESHIDIS discovery. The timer is installed but
disabled because SMTP/email env keys are missing.

## Instruction

Implement the next small gate:

1. Stabilize `eshidis_active_search` source fingerprint so transient page or
   timeout differences do not force bounded discovery when no new active row is
   detected.
2. Run repeated droplet-side scheduled dry-runs and prove that unchanged
   sources skip without full discovery or OpenAI calls.
3. Inspect the droplet `.env.local` keys without printing secret values.
4. Add or confirm required outbound email settings outside chat.
5. Run one controlled real-send smoke to the owner address and confirm
   `notification_log` changes only after success.
6. Enable `tender-radar-scheduled.timer` only after both the skip behavior and
   email send are verified.

## Required Closeout

1. Run at least two consecutive droplet-side dry-run smokes through `ssh`, not
   through a temporary tunnel.
2. Show elapsed time and stage summaries proving no unnecessary OpenAI rerun.
3. Run real-send smoke only when env is present.
4. Report `systemctl` timer status and latest audit report path.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
