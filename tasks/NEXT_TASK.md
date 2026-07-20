# NEXT TASK

Execute:
`Run production reverse-pricing storage audit before any cleanup/refetch apply`

## Current Input

The independent reverse-pricing workflow remains disconnected from cron. The
current baseline is the broader guarded parsing flow plus the new essential
heavy-file retention policy:

- keep local heavy files only for invitations, declarations, technical
  reports/descriptions, standalone budgets, and documents whose extracted text
  proves they contain the analytical budget;
- keep source URLs, text artifacts and provenance for secondary material;
- skip drawings and non-budget studies as pricing candidates unless they
  contain explicit budget evidence in extracted text.

Use storage audit before any live mutation:

```bash
tender-radar pricing storage-audit --db data/tender_radar.sqlite \
  --report work/reports/pricing_storage_audit_YYYYMMDD.json
```

Then dry-run cleanup/refetch:

```bash
tender-radar pricing storage-repair --db data/tender_radar.sqlite \
  --work-dir work/pricing \
  --report work/reports/pricing_storage_repair_dry_run_YYYYMMDD.json
```

Only after reviewing the report and taking a SQLite backup, use:

```bash
tender-radar pricing storage-repair --db data/tender_radar.sqlite \
  --work-dir work/pricing --apply \
  --report work/reports/pricing_storage_repair_apply_YYYYMMDD.json
```

After storage cleanup/refetch, the reprocess command remains:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --report work/reports/pricing_reprocess_existing_YYYYMMDD.json
```

Optional guarded AI fallback exists, but it is only row extraction support:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --use-ai-fallback --ai-fallback-mode empty
```

AI output must still pass local row arithmetic and official document subtotal
validation before rows can complete a project.

Optional AI budget routing is also available:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --use-ai-budget-router
```

The router selects the likely budget document/page range and stores audit
metadata. It does not write rows. If routed parsing fails validation, the
command falls back to full deterministic reprocess.

## Latest Live Audit

Before the `v0.1.44` guard, a depth-1 reverse-pricing UI run on the droplet
found 156 active ESHIDIS candidates, selected one new project (`221155`) and
stopped as intended. Fetch/index finished, but the merged budget validation was
`MISMATCH`; under the new guard this must be counted as partial/review rather
than completed.

After deploy, deterministic reprocess of the current SQLite base reported:

- `projects_seen`: `20`
- `completed`: `9`
- `needs_review_or_failed`: `11`
- `documents`: `515`
- `merged_rows`: `1082`

Review buckets:

- no documents: `220133`, `221381`
- row arithmetic or document-total mismatch: `219795`, `220220`, `220423`,
  `220675`, `221006`, `221155`, `221368`, `221452`, `221720`

Before running AI router across the full base again, add per-project progress
logging/checkpoint reporting or run it in small explicit batches. The previous
full AI-router attempt was stopped after several minutes with no progress
report, and the SQLite backup was restored.

Previous budget extraction state:

- `OK`: `9`
  - `221148`
  - `221233`
  - `221369`
  - `221580`
  - `221615`
  - `221639`
  - `221689`
  - `221691`
  - `221695`
- `NEEDS_REVIEW`: `10`
  - `219795`
  - `220133`
  - `220220`
  - `220423`
  - `220675`
  - `221006`
  - `221368`
  - `221381`
  - `221452`
  - `221720`

Important validation fixes already deployed:

- category-prefixed budget rows;
- split `m2`/`m3` units;
- Greek dot thousands;
- wrapped numeric-prefix rows from archived documents;
- sparse OCR rows;
- OCR-corrupted `ΣΥΝΟΛΟ`;
- collapsed OCR stream rows;
- official subtotal candidate ranking;
- project-total selection before trailing `Π2: 0,00`;
- rejection of quantity-only totals such as `170,51τμ`.
- local standalone official budget/pro-measurement route priority;
- local stale heavy-file path cleanup after deleted downloaded PDFs;
- local Greek filename repair for ZIP members.
- local essential-document heavy file retention rule for invitations,
  declarations, technical descriptions/reports, budgets, pro-measurements and
  price schedules.

## Instruction

Before building new reverse-pricing features, classify the remaining 10 review
projects into evidence-backed buckets.

For each project, report one of:

- `OK`
- `NEEDS_PARSER_FIX`
- `SOURCE_NOT_PRICING`
- `NO_PUBLIC_ATTACHMENTS`
- `MANUAL_REVIEW_REQUIRED`

Do not mark a project `OK` unless:

1. merged row arithmetic passes, and
2. merged row sum reconciles with an official monetary subtotal from the
   extracted source documents.

## Suggested Next Gate

1. Deploy `v0.1.49`, then run production read-only `storage-audit`.
2. If the audit is sane, create a SQLite backup and run dry-run
   `storage-repair`.
3. Apply storage repair only after the dry-run identifies exact affected
   projects and attachments.
4. Reprocess affected projects and classify remaining review projects.
5. Continue with the review set: `219795`, `220133`, `220220`,
   `220423`, `220675`, `221006`, `221368`, `221381`, `221452`, `221720`.

Previous next gate, still relevant after storage repair:

1. Clean or refetch stale `pricing_documents.local_path` rows for older
   reverse-pricing projects, prioritizing essential documents.
2. Keep `219930` as the accepted lump-sum regression fixture: it is `OK` with
   one merged row totaling `2.988.598,87`.
3. Add parser or AI-assisted fixes only for confirmed generic layouts, one at
   a time.

## Required Tests

- Focused `tests/test_pricing.py` after every parser/audit rule change.
- Regression tests for each new generic parser layout fixed.
- Live read-only SQLite audit before and after any live reprocess.

## Required Closeout

1. Update `docs/PROGRESS.md` with fixed/classified project ids and evidence.
2. Update `docs/DECISIONS.md` only for a real product/architecture decision.
3. Update `docs/HANDOFF.md` if production/deployment state changes.
4. Update this file with the next single executable gate.

## Future Backlog

- Pricing UI autocomplete for article codes/descriptions.
- Filters by article/revision code, operator, quantity, unit price and amount.
- Optional AI extraction only for ambiguous budget/table rows.
- Pricing cron only after manual nationwide pricing runs are stable and
  bounded.
