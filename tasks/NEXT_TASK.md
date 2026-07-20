# NEXT TASK

Execute:
`Repair reverse-pricing projects until budget audits are OK`

## Current Input

The independent reverse-pricing workflow is deployed at runtime version
`0.1.36` and remains disconnected from cron.

Production deploy on commit `6a88b18` made pricing completion strict and added
a download-free repair command:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --report work/reports/pricing_reprocess_existing_YYYYMMDD.json
```

The repair command reuses existing `pricing_documents.text_path` artifacts,
rebuilds raw `pricing_budget_rows`, reconsolidates the merged budget and
updates the persisted audit. It skips projects that already have a full OK
audit unless `--all` is supplied.

Strict completion rules:

- A project is skipped as `SKIPPED_ALREADY_COMPLETE` only when it has
  downloaded/indexed documents, merged budget rows, and a persisted
  `pricing_budget_audit` where both:
  - `amount_validation.ok = true`
  - `document_total_validation.ok = true`
- Projects with row arithmetic failures, document subtotal mismatches,
  missing subtotal references or no merged budget audit are not considered
  complete and remain eligible for a later bounded run or force reprocess.
- The document subtotal validator now scans all extracted text documents for
  the project, so subtotals found in οικονομική προσφορά documents can validate
  rows parsed from budget/study documents.
- Generic parser repairs already deployed:
  - category-prefixed budget rows such as
    `ΟΔΟ Α-2 1 Α1 ... ΟΔΟ-1123Α m3 300 3,55 1.065,00`;
  - split `m2`/`m3` where OCR places the exponent on an adjacent line;
  - Greek dot thousands such as `1.200` -> `1200`.

Live SQLite re-audit after deploy:

- `OK`: `7` projects
  - `221233`
  - `221369`
  - `221580`
  - `221615`
  - `221639`
  - `221689`
  - `221691`
- `NEEDS_REVIEW`: `5` projects with parsed rows but non-OK audit
  - `219795`
  - `220220`
  - `220675`
  - `221368`
  - `221720`
- `NO_BUDGET_AUDIT`: `7` projects with no merged pricing budget yet
  - `220133`
  - `220423`
  - `221006`
  - `221148`
  - `221381`
  - `221452`
  - `221695`

## Instruction

Repair the reverse-pricing database before building new pricing features:

1. Pick a small batch from `NO_BUDGET_AUDIT` or `NEEDS_REVIEW`.
2. For each project, inspect the source budget/offer text and the merged rows.
3. Fix only generic parser or audit rules. Do not hardcode project-specific
   values.
4. Re-run consolidation or force reprocess only for the affected projects.
5. Report each project as:
   - `OK`
   - `NEEDS_PARSER_FIX`
   - `SOURCE_NOT_PRICING`
   - `NO_PUBLIC_ATTACHMENTS`
   - `MANUAL_REVIEW_REQUIRED`

Do not mark a project OK unless the database sum reconciles to an official
source subtotal.

## Required Tests

- Focused `tests/test_pricing.py` after every parser/audit rule change.
- Regression tests for each new generic parser layout fixed.
- Live read-only SQLite audit before and after any live reprocess.

## Required Closeout

1. Update `docs/PROGRESS.md` with fixed project ids and evidence.
2. Update `docs/DECISIONS.md` only for a real product/architecture decision.
3. Update `docs/HANDOFF.md` if production/deployment state changes.
4. Update this file with the next single executable gate.

## Future Backlog

- Pricing UI autocomplete for article codes/descriptions.
- Filters by article/revision code, operator, quantity, unit price and amount.
- Optional AI extraction only for ambiguous budget/table rows.
- Pricing cron only after manual nationwide pricing runs are stable and
  bounded.
