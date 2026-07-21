# NEXT TASK

Execute:
`Validate v0.1.52 routing guard against live reverse-pricing review projects`

## Public-Works Cron Prerequisite Completed

Before enabling the scheduled public-works timer, the local public-works
document pipeline was backfilled and made skip-aware:

- `documents analyze` now skips existing usable analysis by default;
- `--force` is required for intentional re-analysis;
- current local state has `137/137` downloaded latest ESHIDIS attachments with
  document analysis rows;
- skip-only verification completed in about `1.0s` with
  `documents_seen=137`, `documents_analyzed=0`, `documents_skipped=137`;
- full test suite passed with `298` tests.

The entalmata stage was also made skip-aware for repeated ADA rows:

- local entalmata state has `111` rows, `5` visible and `106` rejected;
- full entalmata scan completed in about `7.5s` with
  `decisions_seen=240`, `skipped_existing=111`, `errors=0`;
- combined scheduled dry-run with `--recipient smoke@example.test` completed
  in about `132s` with `ok=true`, `errors=[]` and `warnings=[]`.

Production deployment has also been verified on the DigitalOcean droplet:

- GitHub `main` deploy updates `/root/workspace/dimoprasies`;
- latest verified deployed commit: `b662d5b`;
- `tender-radar-scheduled.timer` is `enabled` and `active`;
- the production `.env.local` has the real SMTP/recipient settings;
- production scheduled dry-run completed with `ok=true`;
- entalmata UI/scheduled scan reported `skipped_existing=115`, `errors=0`.

The public-works UI discovery button now has the same source-preflight guard
for completed unchanged backfill windows: when `Backfill safety` is enabled but
sources are unchanged and the previous successful discovery watermark is
complete, `/api/discover` skips the expensive ESHIDIS/KIMDIS steps. The browser
also avoids the follow-up AI/enrichment chain when discovery returns
`skipped=true`.

ESHIDIS attachment downloads are now stored under per-tender directories inside
the configured root, e.g. `work/download_audit/<eshidis_id>/`, to prevent common
filenames from colliding across projects.

Production repair has been applied to the current visible dashboard ESHIDIS
rows: `101/101` preview documents are available, present on disk and sha256
verified; a follow-up non-force download run skipped all `101`.

KIMDIS/authority previews now render linked ESHIDIS documents directly when
local official files exist; ZIP availability is no longer the only indication
for rows such as `26PROC019429074` linked to `ΕΣΗΔΗΣ 207024`.

Public-works dashboard expiry is automatic and datetime-aware: rows with a
parseable deadline and time are hidden after that local deadline time, while
date-only deadlines remain visible until the end of that date. Expired rows are
hidden from the dashboard/email candidate set, not physically deleted.
Expired public-works rows also clean up local downloaded binaries automatically:
ESHIDIS attachment files, KIMDIS source-document files and legacy
KIMDIS/authority index local paths are removed/cleared after expiry, while
official links, ids, extracted text evidence and provenance remain.
Admin audit expired/missing-deadline/duplicate-candidate reasons are restricted
to rows that would otherwise be dashboard candidates. Unrelated ESHIDIS or
authority rows should not be labeled "Ληγμένο" just because they have an old
deadline.
AI-hidden admin audit rows remain visible, but now use semantic AI rejection
categories such as administrative/non-tender, supply/service out of scope, not
public works, or early signal, with the stored AI reason and confidence.
Road-network maintenance tenders are in scope: open tenders for maintenance of
road/provincial networks, including winter maintenance or snow-removal packages
with deadline and budget evidence, should be kept/reviewed by triage rather
than dropped as generic services.
Source health is now tracked from recent polling runs. Do not remove a
public-works source after one HTTP 503; use the admin health status
(`WATCH`, `DEGRADED`, `DISABLE_CANDIDATE`) plus last-success evidence to decide
whether to disable, replace or keep monitoring the source.

Production `26PROC` KIMDIS audit: `9/14` current focus candidates have linked
ESHIDIS ids (`64.3%`). The 5 unresolved rows completed KIMDIS fetch and
connected-acts lookup with `ok=true` but no extracted ESHIDIS id:
`26PROC019476093`, `26PROC019466646`, `26PROC019450787`, `26PROC019449707`,
`26PROC019421668`.

## Current Input

The independent reverse-pricing workflow remains disconnected from cron.
Production storage cleanup/refetch has now run successfully on `v0.1.49`.
`v0.1.52` keeps the `v0.1.51` parser fallback and adds a stricter
document-routing guard. Economic-offer documents are validation-first,
standalone `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` filenames are strong budget evidence, `ΠΥ` is weak
evidence only, and drawings/special studies are skipped before expensive OCR
unless explicit budget evidence is present.

Live targeted reprocess after deploy completed `221720`, which now belongs to
the skipped-complete set. The latest incomplete-set baseline is:

- `projects_seen`: `23`
- `skipped_complete`: `11`
- `projects_inspected`: `12`
- `needs_review_or_failed`: `12`

Next parser work should start from the remaining review buckets, not from
`221720`:

- no public/usable documents: `220133`, `221381`
- zero/near-zero rows despite official offer totals: `221006`, `221314`,
  `221325`, `221452`
- row arithmetic or document-total mismatches: `219795`, `220220`, `220423`,
  `220675`, `221155`, `221368`

Useful command for a targeted project:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --eshidis-id <ESHIDIS_ID> \
  --report work/reports/pricing_reprocess_<ESHIDIS_ID>_YYYYMMDD.json
```

Current live storage state after apply:

- `706` pricing documents
- `65` desired-preserved documents
- `443` local files
- `0` stale local paths
- `0` `needs_refetch`
- `0` stale non-preserved paths

The current baseline is the broader guarded parsing flow plus the essential
heavy-file retention policy:

- keep local heavy files only for invitations, declarations, technical
  reports/descriptions, standalone budgets, and documents whose extracted text
  proves they contain the analytical budget;
- keep source URLs, text artifacts and provenance for secondary material;
- skip drawings and non-budget studies as pricing candidates unless they
  contain explicit budget evidence in extracted text.

Use storage audit before any future live mutation:

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

1. Classify the remaining review projects from the clean-storage base into:
   `NEEDS_PARSER_FIX`, `SOURCE_NOT_PRICING`, `NO_PUBLIC_ATTACHMENTS` or
   `MANUAL_REVIEW_REQUIRED`.
2. Continue with the current review set after storage cleanup and v0.1.50:
   `219795`, `220133`, `220220`, `220423`, `220675`, `221006`, `221155`,
   `221314`, `221325`, `221368`, `221381`, `221452`, `221720`.
3. Prioritize deterministic parser/layout investigation. A targeted
   `--use-ai-fallback --ai-fallback-mode empty` smoke on `221314`, `221325`
   and `221452` produced `0` analytical rows, despite official total evidence
   in economic-offer documents.

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
