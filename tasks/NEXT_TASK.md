# NEXT TASK

Execute:
`Smoke active ESHIDIS pricing batch from UI and promote run audit visibility`

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
- Live smoke for ESHIDIS `221326` covers decimal `Α.Τ.` layouts with local
  numbering that restarts by category and article suffixes split to the next
  line. The parser extracts all `133` merged rows from
  `1 Προυπολογισμός Μελετη_ΙΣΟΓΕΙΟ ΗΡΩΩΝ ΠΟΛΥΤΕΧΝΕΙΟΥ signed.pdf`, with no
  missing row numbers and amount total `354.581,22`.
- Live smoke for ESHIDIS `221271` covers bundled `ΜΕΛΕΤΗ...pdf` budget sources,
  integer quantities, `Αρ. Τιμ.` work-budget layouts and units such as `t` and
  `tkm`. The parser extracts `86` merged rows from
  `ΜΕΛΕΤΗ συντηρηση και επισκευη αυλειων χωρων 7_2021_Π_Μ_Π.pdf`, with no
  missing row numbers and corrected amount total `1.275.390,42`.
- Merged budget consolidation now validates every row amount with
  `quantity * unit_price ~= amount`, allowing small display-rounding
  differences. The same scoring is used to choose between duplicate row-number
  candidates, which fixed `221271` row `3`.
- Batch smoke with `221326`, `221271`, `221473`, `221689`, `221691` and
  `221744` showed skip-existing behavior for the first two and clean full
  ingest for the four new ids. Manual budget quality audit confirmed that the
  merged works subtotals match the official budget subtotals for the new ids.
- `221566` exposed a partial-state recovery case: raw budget rows existed but
  the merged project budget was missing. `pricing ingest-eshidis` now detects
  that state and consolidates locally without refetching, returning
  `PARTIAL_PROJECT_RECOVERED_WITHOUT_REFETCH`.
- Active ESHIDIS pricing batch controller is implemented for CLI and UI:
  `pricing ingest-active` discovers active ESHIDIS rows and ingests every
  returned candidate; `pricing ingest-active-report` replays an existing
  discovery report; `/api/pricing/ingest-active` starts the same flow as a
  background UI job for `admin`/`pricing` roles.
- Batch completion is strict. A run stores `pricing_runs.summary_json` with
  one item per selected candidate and reports `INCOMPLETE` if any selected
  project is partial/failed, if an identifier is invalid, or if an explicit
  `project_limit` leaves candidates unprocessed.
- The reverse-pricing UI uses ESHIDIS discovery depth `500` by default and
  does not pass a project limit from the normal button.
- Reverse-pricing UI now asks for `Νέα έργα` separately from the ESHIDIS
  discovery window. The run skips already complete projects without consuming
  that quota and continues until it reaches the requested number of new or
  incomplete projects, or the discovered active window is exhausted.
- Active ESHIDIS discovery now uses the public `Εξαγωγή σε Excel` grid action
  as the primary source for reverse-pricing candidates. Live smoke with
  `--limit 100` parsed `166` exported active rows and returned `100`
  candidates, while the visible browser grid still exposed only `25`.
- UI sessions are persisted in SQLite by hashed token, so a reload or service
  restart can restore the authenticated session until the 12-hour cookie
  expires. Logout deletes the persistent session.
- Focused discovery/pricing suite passed: `25 passed`.

The reverse-pricing workflow is intentionally separate from the local
`ΔΗΜΟΣΙΑ ΕΡΓΑ` dashboard and is not attached to the six-hour cron yet.

## Instruction

Complete the next gate:

1. Run a live active-ESHIDIS pricing smoke from the UI or CLI with a small
   explicit `project_limit` and verify that the run is marked `INCOMPLETE`
   while every selected item has an outcome.
2. Run the same command without `project_limit` only after the smoke is clean,
   and verify that every discovered active ESHIDIS candidate is either
   completed, skipped as already complete, or explicitly marked partial/failed.
3. Keep reverse-pricing manual; do not attach it to the six-hour cron yet.

## Required Tests

- Focused tests for active pricing batch run accounting, including
  failed/partial outcomes, explicit `project_limit` incompleteness and
  `max_new_projects` continuing past already complete candidates.
- Focused tests that already complete pricing projects are skipped without
  re-fetching.
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
- Regression test that decimal `Α.Τ.` budget layouts with split Greek article
  suffixes and bundled `ΜΕΛΕΤΗ` documents remain pricing candidates.
- Regression test that interrupted runs with raw pricing rows but no merged
  budget recover locally without refetching ESHIDIS.
- Regression test that merged row amount validation reports exact mismatched
  rows and that duplicate row-number candidates prefer the amount-valid row.
- Live smoke check for `221326` and `221271` after parser changes, until these
  layouts are covered by smaller fixtures.
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
