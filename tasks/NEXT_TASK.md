# NEXT TASK

Execute:
`Deploy and verify the official standalone budget route guard`

## Current Input

The independent reverse-pricing workflow is deployed on commit `3f52737`.
It remains disconnected from cron.

The repair command is:

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

After deploy of `v0.1.41`, the read-only router shortlist correctly ranked
`ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf` for `220675` first, but the AI response still
selected a nested ZIP summary because the standalone file had no extracted
snippets in the current database. Local `v0.1.42` adds a deterministic
post-AI guard that overrides this case to the standalone official attachment.
Live `v0.1.42` smoke on the droplet selected `document_id 300`
`ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf`. It still needs targeted re-ingest/reprocess
before `220675` can be reclassified because the standalone local PDF path is
missing from earlier heavy-file cleanup:

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

1. Targeted re-ingest/re-route `220675`. The standalone official PDF must be
   preserved locally before row extraction/reconciliation.
2. Reprocess `220675` from `ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf` and determine
   whether it can reconcile to a trusted monetary subtotal.
3. Inspect `221720` next. It has many parsed rows but appears to be reading a
   price-list/table with many `quantity = 1` rows rather than the actual
   project budget. Add a generic guard if this pattern is confirmed.
4. Then inspect the zero/near-zero row cases: `220133`, `221006`, `221381`,
   `221452`.
5. Only after classification, add targeted parser or AI fallback improvements
   for one confirmed generic layout at a time.

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
