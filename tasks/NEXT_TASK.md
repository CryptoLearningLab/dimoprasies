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
- `tender-radar pricing ingest-eshidis` is skip-aware: repeated runs reuse
  existing downloads and indexed documents unless `--force` is passed.
- Non-pricing ESHIDIS attachments are stored as provenance with
  `SKIPPED_NON_PRICING_DOCUMENT` and skipped on subsequent pricing runs.
- Live smoke for ESHIDIS `221473` fetched `10` attachments and now extracts
  all `10` budget rows from `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf`. This covers split `m3` units
  (`m` plus next-line `3`), starred unit prices and table headers where
  `Τιμή Μονάδας` appears before `Ποσότητα`.
- Live smoke for ESHIDIS `221689` covers a second budget-table layout where
  numbering restarts inside sections and the true global `Α.Τ.` appears before
  the unit column. The parser now extracts `41` merged rows, has no missing row
  numbers, handles split article code `ΝΑΟΔΟ Ε01.2.3`, and totals
  `422.052,75`.
- A repeat `221689` run is skip-aware: `downloaded 0`, `skipped_download 9`,
  `skipped_indexed 9`, `failed 0`.
- Live smoke for ESHIDIS `221691` covers special-unit budget rows and
  backslash article suffixes. The parser now extracts all `56` merged rows from
  `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΣΥΝΤ ΝΑΥΠ ΘΕΡΜΟΥ 2026 2027 signed.pdf`, with no missing row
  numbers and amount total `1.062.649,50`.
- Full local suite passed: `237 passed`.

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
4. Extract text and run the budget parser on likely budget/timologio PDFs,
   using cross-document merge to fill row gaps before expensive OCR.
5. Persist metadata, extracted text references, raw document rows and merged
   project budget rows.
6. Delete heavy PDF/ZIP payloads the same day after successful extraction,
   while keeping structured rows, text and provenance.
7. Keep this manual; do not attach it to the six-hour cron yet.

## Required Tests

- Focused tests for pricing fetch run state and same-day cleanup behavior.
- Focused tests that the fetcher refuses to run against KIMDIS/authority
  sources in this first gate.
- Regression test for skip-existing behavior on repeated
  `pricing ingest-eshidis` runs.
- Regression test that the budget fixture still extracts `Β18.6`.
- Regression test that project-level merged rows are preferred by pricing
  search.
- Regression test that structured budgets using a separate `Α.Τ.` column and
  split article codes do not reuse local section numbering as row numbers.
- Regression test that split `m3` units, starred unit prices and
  price-before-quantity budget headers still extract all rows.
- Regression test that special units such as `ΗΜ/Σ` and `Kgr`, plus backslash
  article suffixes such as `Α\ΝΑ01.1`, still extract correctly.
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
