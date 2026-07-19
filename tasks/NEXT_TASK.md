# NEXT TASK

Execute:
`Implement controlled nationwide ESHIDIS pricing fetcher`

## Current Input

Local version `0.1.36` starts the independent reverse-pricing foundation:

- `admin`, `pricing`, `tester`, `user` roles are accepted.
- `pricing` is reserved for the reverse-pricing module.
- New independent SQLite tables exist for pricing projects, documents, budget
  rows, article aliases and pricing runs.
- `tender-radar pricing parse-budget` extracts structured rows from a budget
  PDF into SQLite.
- The uploaded budget fixture was parsed successfully, including `Β-18.6`:
  description, revision split `30/40/30`, unit `m`, quantity `100`, unit price
  `1680`, amount `168000`.
- Full local suite passed: `230 passed`.

The reverse-pricing workflow is intentionally separate from the local
`ΔΗΜΟΣΙΑ ΕΡΓΑ` dashboard and is not attached to the six-hour cron yet.

## Instruction

Complete the next gate:

1. Add a manual, bounded nationwide ESHIDIS-only fetcher for active public
   works whose submission deadline is after the current fetch date/time.
2. Store discovered projects in the pricing tables without touching the local
   public-works dashboard state.
3. For each fetched project, download only the files needed for extraction
   into a pricing-specific temporary work directory.
4. Extract text and run the budget parser on likely budget/timologio PDFs.
5. Persist metadata, extracted text references and `pricing_budget_rows`.
6. Delete heavy PDF/ZIP payloads the same day after successful extraction,
   while keeping structured rows, text and provenance.
7. Keep this manual; do not attach it to the six-hour cron yet.

## Required Tests

- Focused tests for pricing fetch run state and same-day cleanup behavior.
- Focused tests that the fetcher refuses to run against KIMDIS/authority
  sources in this first gate.
- Regression test that the budget fixture still extracts `Β18.6`.
- Full test suite before production deploy.

## Required Closeout

1. Update `docs/PROGRESS.md` with implementation and smoke evidence.
2. Update `docs/DECISIONS.md` only if the fetch architecture introduces a real
   product/engineering decision.
3. Update `docs/HANDOFF.md` if production/deployment state changes.
4. Update this file with the next single executable gate.
5. Do not enable cron for pricing until explicitly approved after smoke.

## Future Backlog

- Build the pricing UI with autocomplete for article codes/descriptions.
- Add filters by article/revision code, operator, quantity, unit price and
  amount.
- Add optional AI extraction only for ambiguous budget/table rows.
- Add cron only after manual nationwide pricing runs are stable and bounded.
