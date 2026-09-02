# Process Audit ExecPlan - 2026-09-02

## Purpose

Reconcile the project documents with the actual local and production state, so
the next session can continue without relying on chat memory.

## Current State

Local `main` is clean after commit `cafdca1`. Production is deployed at
`cafdca1`, with `tender-radar-ui.service` active and
`tender-radar-scheduled.timer` active. The latest scheduled run completed with
`ok=true` and `monitoring_status=WARNING`.

## Scope

- Verify local git/database state.
- Verify production deploy, service, timer and scheduled report state.
- Record current status for Main Tender Radar, Reverse Pricing, GEO_AFOI and
  repo hygiene.
- Update handoff/progress/decision/next-task docs.

## Milestones

1. Read canonical docs and repo instructions.
2. Inspect local git, SQLite and GEO_AFOI runtime state.
3. Inspect production deploy, systemd timer/service and scheduled report.
4. Update documents with current state and next actions.
5. Run validation and record outcome.

## Data and Interfaces

- Local repo: `/root/dimoprasies`.
- Production repo: `/root/workspace/dimoprasies` on
  `codex-crisp-hawk-a759`.
- Main database: `data/tender_radar.sqlite`.
- GEO_AFOI database: `geo_afoi_pricing/data/geo_afoi_pricing.sqlite`.
- Production report: `work/reports/scheduled_poll_alert_latest.json`.

## Validation

- `git status --short --branch`
- `.venv/bin/python -m pytest -q`
- Production `systemctl status tender-radar-ui.service`
- Production `systemctl list-timers tender-radar-scheduled.timer`
- Production dashboard/email dry-run payload from `src/tender_radar/ui_server.py`

## Progress

- Canonical docs and current task state read.
- Local and production state inspected.
- Production deploy fetch problem was repaired in the droplet script by setting
  `GIT_SSH_COMMAND` to the existing GitHub deploy key.
- Code/test commit `cafdca1` deployed through GitHub Actions successfully.
- Handoff, progress, decisions, known limitations, available mechanisms and
  next-task docs were updated with the audited state.
- Full local test suite passed after the documentation update.

## Decisions

Production deploy fetches must use the explicit droplet GitHub key. This is
recorded as D-140 in `docs/DECISIONS.md`.

## Discoveries and Risks

- Main Tender Radar is operational, but the latest scheduled report is a
  warning because source polling had `1` source error and `3` source health
  warnings.
- Dashboard candidates are not `VERIFIED_ACTIVE`; the current production
  summary reports `verified_active=0`.
- Reverse Pricing has local pilot data but no `pricing_budget_audit` state in
  the inspected database and must not be treated as completed production.
- GEO_AFOI has `151` usable rows and `4` `NEEDS_REVIEW` rows before expanding
  the inventory.

## Outcome

Completed. The repository documents now record the current production,
Reverse Pricing, GEO_AFOI and repo-hygiene state. Validation:

```bash
.venv/bin/python -m pytest -q
# 343 passed in 46.09s
```
