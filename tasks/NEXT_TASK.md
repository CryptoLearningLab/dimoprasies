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
- `tender-radar pricing ingest-eshidis 221566` now fetches official ESHIDIS
  metadata, downloads attachments into pricing-specific storage and expands
  ZIP/RAR bundles.
- Local reprocess of ESHIDIS `221566` proved cross-document budget merging:
  `ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ.pdf` supplied rows `1-27`, `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf` supplied
  rows `12-36`, and the merged project budget produced rows `1-36` with no
  missing row numbers and amount total `2.466.374,00`.
- Pricing search prefers the merged project budget source when present so
  duplicate rows from source documents are not shown as separate matches.
- Full local suite passed: `233 passed`.

The reverse-pricing workflow is intentionally separate from the local
`ΔΗΜΟΣΙΑ ΕΡΓΑ` dashboard and is not attached to the six-hour cron yet.

## Instruction

Complete the next gate:

1. Add skip-aware download/reprocess behavior to `pricing ingest-eshidis` so
   repeated runs reuse already fetched files and already extracted archives
   unless `--force` is explicitly requested.
2. Add a manual, bounded nationwide ESHIDIS-only fetcher for active public
   works whose submission deadline is after the current fetch date/time.
3. Store discovered projects in the pricing tables without touching the local
   public-works dashboard state.
4. For each fetched project, download only the files needed for extraction
   into a pricing-specific temporary work directory.
5. Extract text and run the budget parser on likely budget/timologio PDFs,
   using cross-document merge to fill row gaps before expensive OCR.
6. Persist metadata, extracted text references, raw document rows and merged
   project budget rows.
7. Delete heavy PDF/ZIP payloads the same day after successful extraction,
   while keeping structured rows, text and provenance.
8. Keep this manual; do not attach it to the six-hour cron yet.

## Required Tests

- Focused tests for pricing fetch run state and same-day cleanup behavior.
- Focused tests for skip-existing behavior on repeated `pricing ingest-eshidis`
  runs.
- Focused tests that the fetcher refuses to run against KIMDIS/authority
  sources in this first gate.
- Regression test that the budget fixture still extracts `Β18.6`.
- Regression test that project-level merged rows are preferred by pricing
  search.
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
