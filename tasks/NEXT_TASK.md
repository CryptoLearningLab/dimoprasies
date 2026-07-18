# NEXT TASK

Execute:
`Production env and real scheduled email smoke`

## Current Input

The UI now exposes:

- version badge `v0.1.3`
- SQLite-backed source polling audit
- email alert path `/api/email-alerts`
- SQLite de-duplication through `notification_log`
- CLI scheduled runtime path `tender-radar runtime scheduled-run`
- systemd templates for `tender-radar-scheduled.service` and
  `tender-radar-scheduled.timer`

The scheduled path runs bounded discovery, AI triage, linked-candidate
enrichment and email alerts. It does not run full-depth/backfill discovery
unless explicitly configured.

## Instruction

Implement the next small gate:

1. Inspect the droplet `.env.local` keys without printing secret values.
2. Confirm that OpenAI and outbound email settings required by the runtime are
   present.
3. Install or refresh the systemd service/timer from `deploy/systemd/`.
4. Run a droplet-side scheduled dry-run smoke through SSH.
5. If email env is present, run one controlled real-send smoke to the owner
   address and confirm `notification_log` changes only after success.
6. If email env is missing, do not fake success; document the exact missing
   non-secret key names and keep the timer disabled until configured.

## Required Closeout

1. Run droplet-side dry-run smoke through `ssh`, not through a temporary
   tunnel.
2. Run real-send smoke only when env is present.
3. Report `systemctl` timer status and latest audit report path.
4. Update `docs/PROGRESS.md`.
5. Update `docs/DECISIONS.md` only if a real decision was made.
6. Update this file with the next single executable gate.
7. Update `docs/HANDOFF.md` if project state or next gate changed.
8. Commit and push tracked changes to GitHub unless explicitly told not to.
