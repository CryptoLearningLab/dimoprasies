# Project Progress

## Current Phase
`PHASE_2_SQLITE_VERTICAL_SLICE_PARTIAL`

## Last Updated
`2026-07-20`

## Current Task
`tasks/NEXT_TASK.md`

## Completed Milestones
- The experimental strict `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` filename-only reverse-pricing path
  was reverted after live isolated testing. The 20-candidate smoke found 156
  active ESHIDIS candidates and avoided an OCR storm, but completed only
  `1/20` projects under the strict rule. A follow-up isolated fallback check
  showed `221566` returning to the previous good result (`36` merged rows,
  subtotal `2.466.374,00`, validation `OK`) only when the broader guarded
  parser was used. The project is therefore back on the previous broader
  parsing/reprocess strategy that had `9` validated projects and `11` review
  projects in the latest full deterministic audit.
- Reverse-pricing `v0.1.47` tightens the pre-OCR guard for nested archive
  children. A second live smoke exposed `ΣΤΑΤΙΚΗ ΜΕΛΕΤΗ .zip/ΣΟ3 ΟΠΛΙΣΜΟΙ`
  entering OCR because the archive parent contained `ΜΕΛΕΤΗ`; nested children
  now require their own pricing signal, unless the archive parent has a strong
  budget/pricing signal such as `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ`.
- Live `v0.1.47` guarded force smoke over the first three active ESHIDIS
  candidates completed without the previous OCR storm. `221325` now records
  `41` `SKIPPED_NON_PRICING_DOCUMENT` rows, `6` archive rows and `3` text
  extracted rows; nested drawing files are skipped quickly. The project remains
  partial because no budget rows were parsed from
  `Οικονομική_προσφορά_Έργου_αρ___190626.pdf`, despite a reference total being
  detected there. That is the next parsing issue, not a download/OCR hang.
- Reverse-pricing `v0.1.46` adds a pre-OCR guard for nested drawing PDFs inside
  archive bundles. A live force-refetch stress run exposed ESHIDIS `221325`
  spending many minutes OCR-ing files such as
  `ΣΧΕΔΙΑ ΑΡΧ.ΜΕΛΕΤΗΣ 3 .zip/ΝΕΟ Σ18 signed .pdf` because the child inherited
  the parent `ΜΕΛΕΤΗΣ` word and was incorrectly treated as a pricing document.
  Nested children under drawing archives are now skipped unless the child
  filename itself carries a budget/pricing signal such as `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` or
  `ΤΙΜΟΛΟΓΙΟ`.
- Reverse-pricing `v0.1.45` adds incremental JSONL progress logging for the
  long-running pricing maintenance paths. `pricing ingest-active`,
  `pricing ingest-active-report` and `pricing reprocess-existing` now accept
  `--progress-log`, emitting start/done events per ESHIDIS id with parsed row
  counts, download counts, validation status and running counters. This makes
  full refetch/reprocess runs observable with `tail -f` instead of waiting for
  the final JSON report.
- Reverse-pricing `v0.1.44` tightens active-batch completion status. A project
  can no longer be counted as `COMPLETED` just because budget rows exist; the
  merged budget must also pass local row arithmetic where available and official
  document-total validation. A live depth-1 run on 2026-07-20 found 156 active
  ESHIDIS candidates, selected exactly one new project (`221155`) and stopped
  correctly, but exposed a budget-total `MISMATCH`; this now reports as partial
  so full-base reruns cannot overstate completion.
- After the `v0.1.44` deploy, a deterministic full reprocess of the current
  reverse-pricing SQLite base completed in about 14 seconds. It inspected 20
  projects and reported 9 `OK` and 11 `NEEDS_REVIEW`; no runtime crash occurred.
  The two zero-document projects are `220133` and `221381`, which need fetch
  recovery rather than parsing repair. An attempted `--all --use-ai-budget-router`
  run was stopped after it produced no progress report/log for several minutes;
  the pre-run SQLite backup was restored before the deterministic audit.
- Reverse-pricing `v0.1.43` adds deadline-retention rules for heavy ESHIDIS
  attachments. Essential operational documents such as invitations,
  declarations, technical reports/descriptions, budgets, pro-measurements and
  price schedules remain stored locally while the project is active; secondary
  studies, administrative forms and archives keep provenance/download links and
  extracted text/rows without retaining every heavy file.
- Reverse-pricing `v0.1.42` adds a deterministic AI-router guard for official
  standalone ESHIDIS budget/pro-measurement attachments. If AI selects a nested
  archive summary while an official standalone `ΠΡΟΜΕΤΡΗΣΗ`/`ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ`
  attachment is present, the route is overridden to the official attachment and
  the override is recorded in route warnings/evidence.
- Live `v0.1.42` route smoke for ESHIDIS `220675` now selects
  `ΠΡΟΜΕΤΡΗΣΗ-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf` (`document_id 300`) instead of the nested ZIP
  summary (`document_id 232`). The current database still has the standalone
  local file missing from earlier heavy-file cleanup, so the next gate is
  targeted re-ingest/reprocess from the preserved official standalone PDF.
- Reverse-pricing now has a UI and CLI active-ESHIDIS batch controller. The
  pricing button starts an authenticated background job that discovers active
  ESHIDIS public works, processes every returned candidate unless an explicit
  test `project_limit` is supplied, and persists a `pricing_runs` row with one
  outcome per ESHIDIS id.
- Pricing active batch runs are not allowed to look successful when only a
  subset was processed. Any failure, partial project, invalid identifier or
  explicit project limit marks the run `INCOMPLETE` and reports
  `remaining_unprocessed`.
- The reverse-pricing UI default ESHIDIS discovery depth is now `500`, so a
  normal click covers the current active list size instead of stopping at the
  earlier local smoke size.
- Reverse-pricing UI now separates the active ESHIDIS discovery window from
  the requested number of new/incomplete projects. Already complete pricing
  projects are skipped without consuming the requested new-project quota, so a
  later run can continue past the already indexed front of the active list.
- Reverse-pricing status is now reload-persistent through SQLite. The UI can
  load the latest `pricing_runs` row and live database counts after page
  reload, instead of losing the previous click status when the browser
  client-side message is recreated.
- Reverse-pricing ingest now has a partial-state recovery guard. If a previous
  run has already persisted raw pricing budget rows but was interrupted before
  writing the merged project budget, a repeated `pricing ingest-eshidis` run
  consolidates those rows and returns without re-entering the browser/download
  loop.
- Live partial-recovery smoke for ESHIDIS `221566` completed without refetch:
  `downloaded 0`, `skipped_download 28`, `skipped_indexed 28`,
  `raw_budget_rows_reused 56`, `merged_budget_rows 36`,
  `merged_budget_amount_total 2.466.374,00`, no missing row numbers, guard
  status `PARTIAL_PROJECT_RECOVERED_WITHOUT_REFETCH`.
- Seven-id pricing batch smoke included repeat ids `221326` and `221271`,
  which both skipped existing downloads/indexes. New ids `221473`, `221689`,
  `221691` and `221744` completed full ingest with zero failed attachments and
  no missing merged row numbers. `221566` exposed the partial-state case that
  the new guard now handles.
- Manual quality audit of the new budget documents confirmed that merged
  budget totals match each document's works subtotal before GE/OE,
  contingencies, revision and VAT: `221473` `138.253,83`, `221689`
  `422.052,75`, `221691` `1.062.649,50`, `221744` `1.440.932,40`.
  No omitted row ranges were found in those four budgets.
- Reverse-pricing merge now validates each merged row with
  `quantity * unit_price ~= amount`, allowing small display-rounding
  differences. The validation is included in `merged_budget.amount_validation`
  and reports exact row mismatches when present.
- Amount-aware merge scoring fixed ESHIDIS `221271`: a bad duplicate candidate
  for row `3` (`amount 5,00`) was replaced by the valid row
  `ΟΙΚ Ν8537.2`, `130 * 15,00 = 1.950,00`. The corrected merged works subtotal
  is `1.275.390,42`, matching the six official group subtotals in the bundled
  study PDF.
- Independent reverse-pricing ESHIDIS ingest now downloads official ESHIDIS
  attachments into pricing-specific storage, expands ZIP/RAR bundles, extracts
  text with layout-aware PDF parsing/OCR fallback, stores raw document rows for
  audit and builds a merged per-project budget row set for searchable pricing.
- Live pricing smoke for ESHIDIS `221566` fetched the official project metadata
  and attachment bundle. Local reprocess of the extracted `ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ.pdf`
  and `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf` produced merged rows `1-36`, no missing row numbers
  and amount total `2.466.374,00`, matching the project budget subtotal before
  GE/OE, contingencies, revision and VAT.
- Pricing search now prefers the merged project budget source when present, so
  article searches do not return duplicate rows from multiple source documents.
- The pricing parser avoids expensive OCR fallback when a layout text layer
  already contains many budget rows; missing sections should be resolved by
  cross-document merge before OCR-heavy fallback.
- `tender-radar pricing ingest-eshidis` is now skip-aware. Repeated runs reuse
  existing downloaded files and already indexed documents unless `--force` is
  passed.
- Reverse-pricing ingest now stores non-pricing ESHIDIS attachments as
  provenance with `SKIPPED_NON_PRICING_DOCUMENT` and treats them as processed
  on later runs, so drawings/declarations/irrelevant PDFs do not trigger OCR in
  the default pricing path.
- Live skip smoke for ESHIDIS `221566` reused `25` existing attachments,
  downloaded `0`, failed `0`, and preserved the merged `36` budget rows with
  amount total `2.466.374,00`.
- Live pricing smoke for ESHIDIS `221473` fetched `10` attachments and now
  extracts all `10` rows from `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf`, after adding support for
  split `m3` units (`m` plus next-line `3`), starred unit prices such as
  `27,45*`, and table headers where `Τιμή Μονάδας` appears before
  `Ποσότητα`. The merged amount total is `138.253,83` with no missing row
  numbers.
- Pricing budget parsing now handles structured Greek budget tables where
  local group numbering restarts but the real global `Α.Τ.` row number appears
  immediately before the unit column. It also handles article codes split
  across lines, such as `ΝΑΟΔΟ` on the row and `Ε01.2.3` on the continuation
  line.
- Live pricing smoke for ESHIDIS `221689` fetched `9` attachments and, after
  the structured-table parser fix, extracted `41` merged budget rows with no
  missing row numbers and amount total `422.052,75`, matching the budget
  subtotal before GE/OE, contingencies, revision and VAT. A repeat run
  completed in `7.5s` with `downloaded 0`, `skipped_download 9`,
  `skipped_indexed 9`, `failed 0`.
- Live pricing smoke for ESHIDIS `221691` fetched `8` attachments and now
  extracts all `56` rows from
  `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΣΥΝΤ ΝΑΥΠ ΘΕΡΜΟΥ 2026 2027 signed.pdf`. The parser handles
  special units such as `ΗΜ/Σ` and `Kgr` plus backslash article suffixes such
  as `Α\ΝΑ01.1` and `Α\ΝΔ08.3`. The merged amount total is `1.062.649,50`
  with no missing row numbers.
- UI discovery flow now starts a real OpenAI-backed `sources ai-triage-report`
  job from `/api/ai-triage` after bounded discovery, using the existing
  `OPENAI_API_KEY` in `.env.local` without exposing the secret.
- Bounded discovery then runs non-ESHIDIS candidate enrichment as a separate
  background job: visible KIMDIS/authority rows are fetched, documents are
  inspected for linked ESHIDIS ids and official ESHIDIS folders are fetched
  when an id is found.
- Candidate enrichment writes
  `work/derived/candidate_enrichment_attempts.json` so unchanged rows are not
  reprocessed on later runs.
- Authority/TED numeric identifiers are no longer treated as official ESHIDIS
  ids unless the row has explicit ESHIDIS/eprocurement provenance.
- PHASE 0 repository bootstrap.
- Python package skeleton under `src/tender_radar`.
- Installable project metadata in `pyproject.toml`.
- CLI entry point `tender-radar` with help, version, config validation,
  schema output and Phase 0 placeholders.
- Configuration loader and validator for repository YAML files.
- Structured JSON logging.
- SQLite schema draft in `src/tender_radar/schema.sql`.
- README with clean install and validation commands.
- PHASE 1 partial source audit.
- Source health helper for the public ESHIDIS works search entry point.
- Authority-page tender reference extraction proof.
- Playwright browser inspection of the public ESHIDIS works search flow.
- Captured Oracle ADF form ids, default status value and search POST shape.
- Repeatable browser audit helper in `tools/eshidis_browser_audit.py`.
- Direct ESHIDIS public resource proof for live tender `221744`.
- Official ESHIDIS attachment listing proof with 8 attachment rows.
- Resource detail and attachment XML parsers with tests.
- SQLite database initialization command.
- ESHIDIS resource audit import command.
- ESHIDIS download audit helper for one attachment row.
- ESHIDIS download audit import command.
- CLI `sources fetch-resource` live command for one ESHIDIS id.
- CLI `sources download-attachment` command for one attachment row.
- CLI `sources download-attachment --row-indexes` and `--all` controlled bulk
  mode with `--limit`, skip-existing behavior and `--force`.
- CLI `documents analyze` for downloaded attachment classification and text
  extraction.
- Optional `docs` dependency group with `pypdf` for PDF text extraction.
- JSON and Markdown document analysis reports under `work/reports/`.
- Full extracted text artifacts under `work/extracted_text/`, linked from
  SQLite through `documents.text_path`.
- CLI `search run` for YAML profile matching against analyzed document text.
- Search hits persisted in `search_runs` and `search_hits`.
- Search matching now prefers full text artifacts and dedupes overlapping
  exact phrase hits by document/context similarity.
- CLI `sources discover-active` audits the public ESHIDIS active-search form,
  parses hidden Oracle ADF XML grid responses and writes JSON/Markdown
  candidate reports.
- Local browser UI server in `tender_radar.ui_server` with a Windows
  `Tender Radar UI.cmd` launcher and buttons for discovery, detail fetch,
  attachment download, document analysis and profile search.
- Positive sample profile `road_maintenance`; negative tested profile
  `rockfall_energy_barrier`.
- Idempotent attachment refresh that preserves existing local path, size and
  SHA-256 metadata for matching filenames.
- Live `221744` tender and 8 latest attachment metadata rows imported into
  `data/tender_radar.sqlite`.
- All 8 official ESHIDIS attachments downloaded through the audited `Λήψη`
  action and persisted with local path, size and SHA-256 metadata.
- Remote Python environment completed with `python3.12-venv`, editable
  `[browser,docs,dev]` install and Playwright Chromium.
- Discovery candidate verification batch imported official ESHIDIS detail
  metadata for `221380`, `221629` and `221675`.
- `sources fetch-resource` now imports official tender metadata even when the
  audit has no parsable attachment table response; such cases keep
  `attachment_rows: null` and import zero attachments.
- `docs/EXECPLAN_SOURCE_AUDIT.md`.
- `docs/SOURCE_AUDIT.md`.
- Remote workspace confirmed at `/root/dimoprasies`.
- GitHub repository `CryptoLearningLab/dimoprasies` initialized and pushed.
- Dedicated deploy key `dimoprasies-codex` created for this repository.
- Project handoff document added at `docs/HANDOFF.md`.
- Temporary UI preview proven through a `localhost.run` tunnel.

## Evidence
- Clean local venv created at `.venv`.
- Editable install succeeded with `python -m pip install -e ".[dev]"`.
- CLI help works: `tender-radar --help`.
- CLI version works: `tender-radar --version` returned `tender-radar 0.1.0`.
- Config validation passed for `locations.yml`, `document_types.yml`,
  `search_request.template.yml` and `search_profiles/rockfall_energy_barrier.yml`.
- Placeholder source commands intentionally fail before source audit.
- `tender-radar sources health --allow-insecure-tls` reached the ESHIDIS public
  works search entry point with HTTP 200 and session evidence.
- Public authority page extraction found ESHIDIS id `219879` and one PDF
  attachment link.
- Browser audit loaded the ESHIDIS form, filled `qryId1:val10::content`, clicked
  `qryId1::search` and captured ADF POST requests containing the tested ids.
- Known ids `219879`, `221439`, `221684` and `219756` did not return visible
  official rows for the tested status/id combinations.
- Public resource URL `resources/search/221744` opened official ESHIDIS tender
  details for a live tender with deadline `07-08-2026 10:00:00`.
- Attachment tab returned official ADF XML table with `_rowCount="8"`.
- `tender-radar sources import-resource-audit work\source_audit\eshidis_resource_audit_221744_full.json --db data\tender_radar.sqlite`
  imported tender id `1`, ESHIDIS id `221744` and 8 latest attachments.
- `tools/eshidis_download_audit.py 221744 --row-index 0 --allow-insecure-tls`
  clicked the first `Λήψη` control and saved the first PDF attachment.
- `tender-radar sources import-download-audit work\source_audit\eshidis_download_audit_221744_0.json --db data\tender_radar.sqlite`
  updated SQLite attachment metadata with size `341861` and SHA-256
  `f27c5fae95b44cf6dbb74fda2bb8bb03098cc3f66b814865bbf7989ef5c067d5`.
- `tender-radar sources fetch-resource 221744 --allow-insecure-tls --db data\tender_radar.sqlite`
  fetched and imported the official tender resource through the main CLI.
- `tender-radar sources download-attachment 221744 --row-index 1 --allow-insecure-tls --db data\tender_radar.sqlite`
  downloaded the budget PDF with size `106889` and SHA-256
  `e385422e3d2b585911d35bf7c52e59d560b627734ab2edb173e257b4a6373130`.
- `tender-radar sources download-attachment 221744 --row-indexes 2,3,4,5,6,7 --limit 8 --allow-insecure-tls`
  downloaded the remaining 6 attachments with zero failures.
- `tender-radar sources download-attachment 221744 --all --limit 8 --allow-insecure-tls`
  skipped all 8 already-downloaded attachments without contacting the download
  action again.
- Repeated `sources fetch-resource` calls preserve existing downloaded
  attachment rows as latest metadata.
- `tender-radar documents analyze --eshidis-id 221744 --report work\reports\document_analysis_221744_with_text.json --markdown-report work\reports\document_analysis_221744.md`
  classified all 8 downloaded attachments and extracted PDF/XML text samples.
- `tender-radar search run --profile config\search_profiles\rockfall_energy_barrier.yml --eshidis-id 221744`
  scanned 3 documents and found 0 matches.
- `tender-radar search run --profile config\search_profiles\road_maintenance.yml --eshidis-id 221744`
  scanned 5 documents and found 20 deduped evidence snippets against full text.
- `tender-radar sources discover-active --allow-insecure-tls --limit 25`
  submitted the public ESHIDIS status filter value `2`, parsed hidden ADF XML
  grid rows and found 15 `DISCOVERED_ACTIVE_CANDIDATE` tender ids with
  deadlines.
- `python3 -m venv .venv` initially failed because `python3.12-venv` was
  missing; `apt update && apt install -y python3.12-venv` fixed the remote
  environment.
- `python -m pip install -e ".[browser,docs,dev]"` and
  `python -m playwright install chromium` completed in the remote environment.
- `python -m tender_radar sources fetch-resource 221380 --allow-insecure-tls`
  wrote `work/source_audit/eshidis_resource_audit_221380.json`, imported tender
  id `3`, captured official deadline `25-07-2026 14:00:00`, and imported
  `0` attachments because no attachment table response was captured.
- `python -m tender_radar sources fetch-resource 221629 --allow-insecure-tls`
  wrote `work/source_audit/eshidis_resource_audit_221629.json`, imported tender
  id `4`, captured official deadline `27-07-2026 10:00:00`, and imported
  `0` attachments because no attachment table response was captured.
- `python -m tender_radar sources fetch-resource 221675 --allow-insecure-tls`
  wrote `work/source_audit/eshidis_resource_audit_221675.json`, imported tender
  id `5`, captured official deadline `27-07-2026 10:00:00`, and imported
  `0` attachments because no attachment table response was captured.
- The selected candidates remain `UNKNOWN` in SQLite with
  `status_confidence = 0.0`; they were not promoted to `VERIFIED_ACTIVE`.
- `python -m tender_radar evaluate run --profile config/evaluation_profiles/public_works_dynamic.yml --eshidis-id 221744 --report work/reports/evaluation_public_works_dynamic_221744_remote.json --markdown-report work/reports/evaluation_public_works_dynamic_221744_remote.md`
  scanned 8 documents, matched 1 tender and wrote the remote sample evaluation
  reports.
- `git push git@github.com:CryptoLearningLab/dimoprasies.git main:main`
  using the dedicated `dimoprasies-codex` key created remote branch `main`.
- `git ls-remote --heads git@github.com:CryptoLearningLab/dimoprasies.git`
  confirmed that `refs/heads/main` exists on GitHub.
- `.venv/bin/tender-radar-ui --host 0.0.0.0 --port 8765` started the local UI
  server.

### 2026-07-20 - Reverse-pricing total validation tightened

The reverse-pricing repair pass now rejects additional false-positive budget
audits instead of inflating the completed count. Generic validation fixes were
deployed in three commits:

- `2659116` tightened official subtotal candidate ranking and de-prioritized
  non-budget source documents.
- `406f353` fixed total amount selection for lines such as
  `Σύνολο Δαπάνης ... Π2: 0,00`, so the validator chooses the project total
  instead of the trailing zero column.
- `25aeebd` ignores quantity-only totals with glued units such as
  `170,51τμ`, preventing area/quantity summaries from being treated as
  official monetary subtotals.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_pricing.py
# 44 passed
```

Production deploy evidence:

- GitHub Actions deploy runs for commits `2659116`, `406f353` and `25aeebd`
  completed successfully.
- Droplet HEAD after the latest deploy: `25aeebd`.
- Droplet focused pricing tests: `tests/test_pricing.py` -> `44 passed`.
- Live reprocess report:
  `work/reports/pricing_reprocess_v0143_quantity_total_guard.json`.
- Current live reverse-pricing audit remains:
  - `OK`: `9`
  - `NEEDS_REVIEW`: `10`

The count did not increase because the pass corrected unsafe audit behavior.
`221006` and `221452` are no longer allowed to look complete with zero parsed
rows, and `220675` no longer compares its parsed total against the non-monetary
quantity line `ΣΥΝΟΛΟ ΧΩΡΩΝ ... 170,51τμ`; it is now correctly
`NO_REFERENCE_TOTAL_FOUND`.
- `curl -L -s https://b608b69a6b7e08.lhr.life` returned the Tender Radar UI
  HTML through a temporary tunnel.
- The temporary tunnel URL is not permanent infrastructure.
- Live Playwright diagnostics showed that `221380`, `221629` and `221675`
  do expose public attachment rows after the ESHIDIS ADF streamed table loads.
- `fetch_resource_audit` now waits for `#t1::db` and download button controls
  after opening the attachments tab, instead of snapshotting too early.
- `python -m tender_radar sources fetch-resource 221380 --allow-insecure-tls`
  re-ran after the wait fix and imported `24` latest attachment rows.
- `python -m tender_radar sources fetch-resource 221629 --allow-insecure-tls`
  re-ran after the wait fix and imported `10` latest attachment rows.
- `python -m tender_radar sources fetch-resource 221675 --allow-insecure-tls`
  re-ran after the wait fix and imported `9` latest attachment rows.
- The UI report endpoint `/api/report?path=candidates.json` now serves
  `application/json; charset=utf-8`; a curl smoke test confirmed Greek text
  such as `ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ` renders as UTF-8 in the JSON body.
- `.venv/bin/python -m tender_radar sources download-attachment 221675 --all --limit 20 --allow-insecure-tls`
  downloaded all 9 official latest attachment rows for `221675` with zero
  failures and stored local path, size and SHA-256 in SQLite.
- `.venv/bin/python -m tender_radar documents analyze --eshidis-id 221675 --report work/reports/document_analysis_221675.json --markdown-report work/reports/document_analysis_221675.md`
  analyzed 9 downloaded documents for `221675`; all 9 produced text artifacts
  under `work/extracted_text/`.
- `.venv/bin/python -m tender_radar evaluate run --profile config/evaluation_profiles/public_works_dynamic.yml --eshidis-id 221675 --report work/reports/evaluation_public_works_dynamic_221675.json --markdown-report work/reports/evaluation_public_works_dynamic_221675.md`
  scanned 9 documents, matched 1 tender, and produced score `14.0` with 6
  evidence hits.
- `221675` remains `UNKNOWN` with `status_confidence = 0.0`; the candidate was
  not promoted to `VERIFIED_ACTIVE`.
- `status verify` was added as a separate advisory status-verification command.
  It checks the official deadline, latest attachment names and analyzed
  document signals, writes JSON/Markdown evidence, and does not update
  `tenders.status`.
- `.venv/bin/python -m tender_radar status verify --eshidis-id 221675 --report work/reports/status_verification_221675.json --markdown-report work/reports/status_verification_221675.md`
  checked 9 latest attachments and 9 analyzed documents. It recommended
  `POSSIBLY_ACTIVE` with confidence `0.65`, found 2 non-decisive procedural
  declaration mentions, and kept `verified_active = false`.
- The generated status reports are:
  `work/reports/status_verification_221675.json` and
  `work/reports/status_verification_221675.md`.
- The local UI first screen was redesigned as a business-facing tender list
  rather than a developer-only phase console. It now combines discovery report
  rows and SQLite metadata through `/api/dashboard`.
- `config/locations.yml` now includes Δήμος Πατρέων and limits the configured
  Central Greece regional focus to Φωκίδα. The default UI scope uses the
  configured local-interest geography; the all-Greece toggle changes only the
  presentation scope and does not claim national completeness.
- The UI now shows essential columns: ESHIDIS id, title, authority, budget,
  submission deadline and official ESHIDIS link. It also exposes `Download
  files` and preview for declaration, technical description and budget when
  known/downloaded attachments exist.
- `docs/AVAILABLE_MECHANISMS.md` records the existing source, download,
  analysis, search, evaluation, status and UI mechanisms.
- UI smoke test:
  - `/` returned the new first screen.
  - `/api/dashboard?scope=focus` returned 1 local-interest visible row from
    20 known/discovered rows.
- `.venv/bin/python -m tender_radar pricing ingest-eshidis 221566 --db /tmp/tender_pricing_221566.sqlite --work-dir /tmp/tender_pricing_221566_work --limit 50 --allow-insecure-tls`
  fetched official metadata for `221566`, found 25 ESHIDIS attachment rows,
  downloaded 25 files and expanded the tender RAR bundle. The first live rerun
  was manually interrupted before final report writing, leaving no running
  process and preserving partial local artifacts for targeted reprocess.
- Targeted local pricing reprocess of `221566`:
  `ΤΕΧΝΙΚΗ_ΕΚΘΕΣΗ.pdf` parsed 27 rows covering row numbers `1-27`,
  `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf` parsed 25 rows covering row numbers `12-36`, and
  `consolidate_pricing_project_budget` produced 36 merged rows, no missing
  rows and amount total `2466374.0`.
- Verification on 2026-07-19:
  `.venv/bin/python -m py_compile src/tender_radar/pricing.py src/tender_radar/cli.py`
  passed.
- Verification on 2026-07-19:
  `.venv/bin/python -m pytest tests/test_cli.py tests/test_pricing.py -q`
  passed with `20 passed`.
- Verification on 2026-07-19:
  `.venv/bin/python -m pytest -q` passed with `233 passed`.
  - `/api/dashboard?scope=all` returned 20 visible rows.
  - `/api/document-preview?eshidis_id=221675` returned 9 documents and featured
    declaration, technical description and budget.
- Imported the uploaded source whitelist into `docs/SOURCE_WHITELIST.md` and
  `config/sources.yml`.
- Added `config/deduplication.yml` and `docs/DEDUPLICATION.md`. Title-only
  matching is explicitly forbidden for merges; repeated titles such as
  `Αναπλάσεις ΔΕ Ναυπάκτου` stay separate unless official identifiers,
  official cross-references or strong composite evidence prove identity.
- Updated `config/locations.yml` with additional whitelist aliases for
  Δωρίδα/Ευπάλιο, Μεσολόγγι, Θέρμο and Πάτρα.
- Updated `AGENTS.md` and `docs/SOURCE_AUDIT.md` so source adapter failures,
  priority-source coverage and provenance remain explicit.
- Added `sources audit-whitelist` for `config/sources.yml`. It writes JSON and
  Markdown reports, checks simple GET reachability, marks POST APIs as
  adapter-required and refuses to fetch URL templates without known official
  identifiers.
- Ran the source whitelist audit against 31 configured entries:
  - reachable: 22
  - failed: 2
  - adapter-required: 10
  - templates requiring identifiers: 4
- The two failed whitelist entries were the Patras municipal tenders page and
  municipal committee decisions page, both timing out during the audit.
- KIMDIS POST sources are now probed through documented request bodies instead
  of being treated as plain searchable URLs.
- Upgraded the whitelist audit to distinguish missing adapters from runtime
  source availability:
  - KIMDIS notice/auction/contract now run documented POST probes with
    `contractType: "10"`.
  - URL templates are marked ready once the official identifier is known.
  - Known ESHIDIS browser flows are tied to existing CLI adapters.
  - Failed municipal pages are marked with fallback when another source for the
    same scope is reachable.
- Latest whitelist audit summary after the adapter/fallback update:
  - reachable: 24
  - failed: 3
  - adapter-required: 0
  - templates requiring identifiers: 4
  - failed with fallback: 2
  - unresolved blockers: 0
- Added `sources expanded-report` for a controlled expanded discovery pass. It
  combines the latest ESHIDIS candidate report with KIMDIS Open Data
  PROC/AWRD/SYMV pages, filters against configured source-scope aliases and
  deduplicates only by official source id.
- Ran a fresh expanded discovery pass:
  - source whitelist: 31 checked, 24 reachable/ready, 0 unresolved blockers
  - ESHIDIS active discovery: 0 candidates in this runtime run
  - KIMDIS Open Data: 5 pages per PROC/AWRD/SYMV family, 750 records total
  - focus-related KIMDIS records: 53
  - focus breakdown: 12 PROC, 22 AWRD, 19 SYMV
  - runtime errors: 0
- Sent the Markdown expanded discovery report to the authenticated Gmail
  account with attachment `work/reports/expanded_discovery_report.md`.
- Added submission-stage classification for KIMDIS records:
  - PROC with `finalSubmissionDate` after the as-of date and not cancelled is
    `SUBMISSION_OPEN_CANDIDATE`.
  - PROC with expired `finalSubmissionDate` is
    `SUBMISSION_EXPIRED_CANDIDATE`.
  - Cancelled PROC is `CANCELLED_NOTICE`.
  - AWRD/SYMV are historical award/contract records, not submission-stage
    tenders.
- Re-ran the expanded report with `--as-of-date 2026-07-17`:
  - focus open PROC candidates: 11
  - focus expired PROC candidates: 0
  - cancelled PROC notices: 1
  - focus historical AWRD/SYMV records: 41
- Added Δήμος Αμφιλοχίας as a focus geography in `config/locations.yml`,
  `config/sources.yml` and `docs/SOURCE_WHITELIST.md`.
- Added 5 public Δήμος Αμφιλοχίας sources:
  - official prokiryxis/procurements category,
  - official invitations of interest category,
  - mayor decisions,
  - municipal council decisions,
  - Diavgeia authority page.
- Re-ran source whitelist audit after adding Amfilochia:
  - total sources: 36
  - reachable/ready: 29
  - failed: 3
  - adapter-required: 0
  - templates: 4
  - failed with fallback: 2
  - unresolved blockers: 0
- Re-ran the expanded report after adding Amfilochia; the current 5-page KIMDIS
  window remained 750 total records, 53 focus records and 11 open PROC
  candidates.
- Added additional Δήμος Αμφιλοχίας aliases for `Θεριακήσι`, `Θεριακήσιο`
  and `Θεργιακήσι`.
- Strengthened UI focus matching normalization with Unicode casefold and
  accent/diacritic removal, matching the expanded-report source matching
  behavior for Greek uppercase/lowercase and accented/unaccented variants.
- Fixed the UI focus filter so configured regions with explicit
  `included_regional_units` match those regional units instead of the broad
  NUTS prefix. This removed a false positive where `EL644 - Φθιώτιδα` was
  counted as `Περιφέρεια Στερεάς Ελλάδας - Φωκίδα`.
- Confirmed the UI dashboard currently reads 20 ESHIDIS/discovery/SQLite rows
  and shows 1 focus match after the fix. This is separate from the emailed
  expanded KIMDIS report, which had 11 `SUBMISSION_OPEN_CANDIDATE` PROC
  notices.
- Integrated `work/reports/expanded_discovery_report.json`
  `focus_open_proc_candidates` into the first-screen UI dashboard. KIMDIS
  PROC rows are displayed as `SUBMISSION_OPEN_CANDIDATE` with `ΚΗΜΔΗΣ` source
  labels, official ADAM ids, budgets, deadlines and attachment links, while
  ESHIDIS-only preview/download actions remain disabled for those rows.
- After the KIMDIS dashboard merge, the focus UI shows 12 rows: 11 KIMDIS open
  PROC candidates plus the existing ESHIDIS `221744` row.
- Connected the first-screen `Νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ` button to a real
  discovery sequence: `sources discover-active`, then `sources
  expanded-report`, then dashboard reload from the newly written reports.
- Tightened the Δωρίδα alias `Γλυφάδα` to `Γλυφάδα Δωρίδος` after a live run
  showed a false positive from Δήμος Γλυφάδας Αττικής.
- Re-ran the real UI discovery sequence after the alias fix:
  - ESHIDIS discovery candidates: 15
  - expanded total candidates: 765
  - expanded focus candidates: 51
  - KIMDIS focus open PROC candidates: 12
  - focus historical AWRD/SYMV records: 37
  - expanded runtime errors: 0
  - UI focus rows: 14, made of 12 KIMDIS rows and 2 ESHIDIS rows.

## Tests Last Run
- `.venv/bin/python -m pytest tests/test_status.py tests/test_cli.py`
- Result: 12 passed.
- `.venv/bin/python -m pytest`
- Result: 44 passed.
- `.venv/bin/python -m pytest tests/test_config.py`
- Result: 1 passed.
- `.venv/bin/python -m pytest tests/test_source_whitelist.py tests/test_cli.py tests/test_config.py`
- Result: 11 passed.
- `.venv/bin/python -m tender_radar sources audit-whitelist --allow-insecure-tls --timeout 8 --report work/reports/source_whitelist_audit.json --markdown-report work/reports/source_whitelist_audit.md`
- Result: 31 checked, 22 reachable, 2 failed, 10 adapter-required, 4 templates.
- `.venv/bin/python -m pytest`
- Result: 45 passed.
- `.venv/bin/python -m pytest tests/test_source_whitelist.py tests/test_cli.py tests/test_config.py`
- Result: 12 passed.
- `.venv/bin/python -m tender_radar sources audit-whitelist --allow-insecure-tls --timeout 8 --report work/reports/source_whitelist_audit.json --markdown-report work/reports/source_whitelist_audit.md`
- Result: 31 checked, 24 reachable, 3 failed, 0 adapter-required, 4 templates, 2 failed-with-fallback, 0 unresolved blockers.
- `.venv/bin/python -m pytest`
- Result: 46 passed.
- `.venv/bin/python -m pytest tests/test_expanded_report.py tests/test_source_whitelist.py tests/test_cli.py tests/test_config.py`
- Result: 15 passed.
- `.venv/bin/python -m tender_radar sources expanded-report --allow-insecure-tls --kimdis-pages 5 --timeout 20 --eshidis-candidates work/reports/eshidis_active_candidates.json --report work/reports/expanded_discovery_report.json --markdown-report work/reports/expanded_discovery_report.md`
- Result: 750 total candidates, 53 focus candidates, 0 errors.
- `.venv/bin/python -m pytest`
- Result: 49 passed.
- `.venv/bin/python -m pytest tests/test_expanded_report.py tests/test_cli.py tests/test_config.py`
- Result: 14 passed.
- `.venv/bin/python -m tender_radar sources expanded-report --allow-insecure-tls --kimdis-pages 5 --timeout 20 --as-of-date 2026-07-17 --eshidis-candidates work/reports/eshidis_active_candidates.json --report work/reports/expanded_discovery_report.json --markdown-report work/reports/expanded_discovery_report.md`
- Result: 750 total candidates, 53 focus candidates, 11 focus open PROC candidates, 0 focus expired PROC candidates, 41 historical AWRD/SYMV records, 0 errors.
- `.venv/bin/python -m pytest`
- Result: 50 passed in 1.87s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m tender_radar sources audit-whitelist --allow-insecure-tls --timeout 8 --report work/reports/source_whitelist_audit.json --markdown-report work/reports/source_whitelist_audit.md`
- Result: 36 checked, 29 reachable/ready, 3 failed, 0 adapter-required, 4 templates, 2 failed-with-fallback, 0 unresolved blockers.
- `.venv/bin/python -m tender_radar sources expanded-report --allow-insecure-tls --kimdis-pages 5 --timeout 20 --as-of-date 2026-07-17 --eshidis-candidates work/reports/eshidis_active_candidates.json --report work/reports/expanded_discovery_report.json --markdown-report work/reports/expanded_discovery_report.md`
- Result: 750 total candidates, 53 focus candidates, 11 focus open PROC candidates, 0 errors.
- `.venv/bin/python -m pytest`
- Result: 50 passed in 1.87s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest tests/test_ui_server.py tests/test_expanded_report.py`
- Result: 13 passed in 0.36s.
- `.venv/bin/python -m pytest`
- Result: 52 passed in 1.35s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest tests/test_ui_server.py`
- Result: 9 passed in 0.25s.
- UI smoke test: `curl -s http://127.0.0.1:8765/api/dashboard?scope=all`
- Result: `total_known: 20`, `visible: 20`, `focus_matches: 1`.
- Tunnel smoke test: `curl -L -s -o /dev/null -w "%{http_code} %{content_type}\n" https://baaf8660f7fa87.lhr.life`
- Result: `200 text/html; charset=utf-8`.
- `.venv/bin/python -m pytest`
- Result: 53 passed in 1.54s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest tests/test_ui_server.py`
- Result: 10 passed in 0.25s.
- Dashboard payload smoke test through `dashboard_payload("focus")`
- Result: `total_known: 31`, `visible: 12`, `focus_matches: 12`.
- UI API smoke test: `curl -s http://127.0.0.1:8765/api/dashboard?scope=focus`
- Result: `total_known: 31`, `visible: 12`, `focus_matches: 12`; first rows include 11 `ΚΗΜΔΗΣ:*` items and `ΕΣΗΔΗΣ:221744`.
- Tunnel smoke test: `curl -L -s -o /dev/null -w "%{http_code} %{content_type}\n" https://baaf8660f7fa87.lhr.life`
- Result: `200 text/html; charset=utf-8`.
- `.venv/bin/python -m pytest`
- Result: 54 passed in 1.11s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest tests/test_ui_server.py`
- Result: 11 passed in 0.35s.
- Real UI search endpoint:
  `curl -s -X POST http://127.0.0.1:8765/api/discover -H 'Content-Type: application/json' --data '{"limit":25}'`
- Result before alias tightening: `ok: true`; `eshidis_discover` returncode 0; `expanded_report` returncode 0; expanded summary `total_candidates: 765`, `focus_candidates: 53`, `focus_open_proc_candidates: 13`.
- `.venv/bin/python -m pytest tests/test_ui_server.py tests/test_expanded_report.py`
- Result: 17 passed in 0.41s.
- Real UI search endpoint re-run after replacing `Γλυφάδα` with
  `Γλυφάδα Δωρίδος`.
- Result: `ok: true`; expanded summary `total_candidates: 765`,
  `focus_candidates: 51`, `focus_open_proc_candidates: 12`,
  `focus_historical_awrd_symv_records: 37`, `errors: 0`; dashboard summary
  `total_known: 32`, `visible: 14`, `focus_matches: 14`.
- `.venv/bin/python -m pytest`
- Result: 56 passed in 1.44s.
- Added `sources fetch-kimdis-open-proc` for official KIMDIS PROC attachment
  fetching from `work/reports/expanded_discovery_report.json`.
- The KIMDIS fetch report stores per-record official id, title, authority,
  budget, final submission date, source URL, attachment URL, local path,
  size, SHA-256, extraction status and document evidence status.
- The fetch command keeps open PROC records as `SUBMISSION_OPEN_CANDIDATE` and
  `ATTACHMENT_*_PENDING_DOCUMENT_REVIEW`; it never emits `VERIFIED_ACTIVE`.
- First live KIMDIS fetch pass checked 12 open PROC candidates, downloaded 9
  PDFs, extracted text from 9 PDFs and failed 3 attachments with
  `HTTP Error 429: Too Many Requests`.
- Retry/backoff and idempotent local skip were added for KIMDIS attachment
  fetching, so already-downloaded official files are inspected locally without
  re-hitting KIMDIS.
- Second live KIMDIS fetch pass checked the same 12 open PROC candidates,
  reused 9 already-present files, downloaded the 3 remaining PDFs, failed 0
  records and extracted text from all 12 PDFs.
- Final KIMDIS shortlist refresh:
  `.venv/bin/python -m tender_radar sources fetch-kimdis-open-proc --expanded-report work/reports/expanded_discovery_report.json --config config/sources.yml --download-dir work/download_audit/kimdis --report work/reports/kimdis_open_proc_fetch_report.json --markdown-report work/reports/kimdis_open_proc_fetch_report.md --limit 12 --timeout 30 --allow-insecure-tls --retries 2 --retry-delay 30 --request-delay 5`
- Final KIMDIS shortlist result: 12 checked, 12 already present, 0 failed,
  12 text extracted, 12 document evidence found, 0 unsupported/unread.
- New KIMDIS tests cover attachment metadata/SHA-256, no title-only merge for
  repeated titles, and document authority/scope evidence from attachment text.
- `.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_cli.py`
- Result: 13 passed in 0.53s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 60 passed in 1.45s.
- `sources fetch-kimdis-open-proc` now also writes a durable KIMDIS document
  index to `work/derived/kimdis_open_proc_documents.json` and full extracted
  text artifacts to `work/extracted_text/kimdis/`.
- The document index preserves official id, title, authority, budget,
  final submission date, source URL, attachment URL, local file path, size,
  SHA-256, retrieval timestamp, candidate-only status and document evidence.
- The UI dashboard now joins KIMDIS open PROC rows with the document index.
  KIMDIS rows with local files expose `Preview` and `Download file` actions
  using `/api/kimdis-document-preview?official_id=...` and
  `/api/kimdis-document-file?official_id=...`.
- Live KIMDIS document-index refresh:
  `.venv/bin/python -m tender_radar sources fetch-kimdis-open-proc --expanded-report work/reports/expanded_discovery_report.json --config config/sources.yml --download-dir work/download_audit/kimdis --text-dir work/extracted_text/kimdis --document-index work/derived/kimdis_open_proc_documents.json --report work/reports/kimdis_open_proc_fetch_report.json --markdown-report work/reports/kimdis_open_proc_fetch_report.md --limit 12 --timeout 30 --allow-insecure-tls --retries 2 --retry-delay 30 --request-delay 5`
- Live KIMDIS document-index result: 12 checked, 12 already present, 0 failed,
  12 text extracted, 12 document evidence found and 12 text artifact files.
- UI payload smoke test through Python helpers:
  `dashboard_payload("focus")` returned summary `total_known: 32`,
  `visible: 14`, `focus_matches: 14`, with 12 KIMDIS rows exposing
  local `/api/kimdis-document-file?...` download URLs.
- `kimdis_document_preview_payload("26PROC019466646")` returned an available
  local document with `DOCUMENT_EVIDENCE_FOUND` and a local file URL.
- `.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_cli.py tests/test_ui_server.py`
- Result: 26 passed in 0.82s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 62 passed in 1.41s.
- Added recall-first ambiguous place alias handling for configured source and
  UI focus matching.
- `config/sources.yml` and `config/locations.yml` now model `Γλυφάδα` and
  `Γλυφάδας` as ambiguous aliases for Δήμος Δωρίδος. Positive context such as
  `Δωρίδος`, `Φωκίδα` or `EL645` confirms the match; negative context such as
  `Δήμος Γλυφάδας`, `Αττική` or `EL30` blocks it; otherwise the candidate is
  retained for review with a match note.
- Added `match_notes` to expanded discovery candidates so ambiguous retained
  matches are visible in reports and UI rows.
- Added config validation for optional `ambiguous_aliases` entries.
- Alias-risk inventory found additional watchlist aliases: `Κατοχή`,
  `Ρίο` and `Ιτέα`. They remain exact-token matches, not substring matches;
  no immediate recall-blocking change was needed.
- Duplicate aliases `Δωρίδα` and `Ευπάλιο` appear in both the Δήμος Δωρίδος
  scope and the Π.Ε. Φωκίδας regional scope. This is intentional overlap, not
  title-only deduplication.
- Live expanded-report re-run after the ambiguity change:
  `.venv/bin/python -m tender_radar sources expanded-report --allow-insecure-tls --kimdis-pages 5 --timeout 20 --as-of-date 2026-07-17 --eshidis-candidates work/reports/eshidis_active_candidates.json --report work/reports/expanded_discovery_report.json --markdown-report work/reports/expanded_discovery_report.md`
- Result: `total_candidates: 765`, `focus_candidates: 51`,
  `focus_open_proc_candidates: 12`, `focus_historical_awrd_symv_records: 37`,
  `errors: 0`; current live dataset has 0 ambiguous `match_notes`.
- UI smoke through `dashboard_payload("focus")`: `total_known: 32`,
  `visible: 14`, `focus_matches: 14`, with 12 KIMDIS rows.
- `.venv/bin/python -m pytest tests/test_config.py tests/test_expanded_report.py tests/test_ui_server.py`
- Result: 22 passed in 0.52s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 65 passed in 1.44s.
- Updated the UI table so `Α/Α` and `Πηγή` are separate columns, improving
  mobile readability where KIMDIS ADAM ids and source labels previously
  collided.
- Added a KIMDIS/ADAM input group on the `Εργαλεία` page with `Preview KIMDIS`
  and `Fetch KIMDIS files` actions. The fetch action runs the existing
  candidate-only KIMDIS open PROC attachment flow and refreshes the document
  index/text artifacts.
- Changed ESHIDIS and KIMDIS preview rendering to show all available documents
  in the preview pane instead of only the featured declaration/technical
  description/budget subset. The ESHIDIS `Download files` button continues to
  call `sources download-attachment --all --limit 50`.
- `.venv/bin/python -m pytest tests/test_ui_server.py`
- Result: 14 passed in 0.41s.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 66 passed in 1.46s.

## Open Problems
- Η αναζήτηση grid του ΕΣΗΔΗΣ παραμένει δύσκολη/virtualized, αλλά το direct
  `resources/search/{id}` αποδείχθηκε καλύτερο πρώτο adapter target.
- Το κουμπί `Λήψη` έχει αποδειχθεί για όλα τα 8 συνημμένα του `221744` και
  όλα τα 9 συνημμένα του `221675`, αλλά η κάλυψη άλλων διαγωνισμών θέλει
  περισσότερα δείγματα.
- Η εξαγωγή κειμένου PDF βασίζεται σε `pypdf` και δεν είναι OCR· σκαναρισμένα
  PDF μπορεί να θέλουν ξεχωριστή OCR φάση.
- Το πρώτο search κάνει phrase/term matching με βασικό dedup. Δεν έχει ακόμη
  stemming, semantic scoring ή tender-level final score.
- Το Python TLS verification αποτυγχάνει στο τρέχον environment για δημόσιες
  HTTPS πηγές· χρειάζεται CA bundle/trust-store fix πριν από production fetches.
- Δεν υπάρχει ακόμη full source adapter, document parser, database migration
  runner ή export generator.
- Η συνδρομητική πλατφόρμα ΤΕΕ είναι πιθανή authenticated source, αλλά δεν
  πρέπει να αποθηκευτούν κωδικοί στο repo.
- Το fallback YAML parser καλύπτει τα τρέχοντα config shapes· για πλήρη YAML
  συνιστάται το dev/yaml extra με PyYAML.
- Το public tunnel για UI είναι προσωρινό και ακατάλληλο για μόνιμη χρήση.
  Για καθημερινή χρήση προτιμώνται local, LAN, Tailscale ή Synology deployment.
- Το source whitelist audit αποδεικνύει adapter/readiness και fallback
  availability, όχι ακόμη πλήρη συλλογή/εισαγωγή όλων των έργων στη βάση.
  Η Πάτρα έχει δύο προσωρινά timeout σελίδων, αλλά υπάρχουν reachable fallback
  πηγές για το ίδιο scope.
- Το expanded report είναι discovery/candidate report. Τα KIMDIS PROC/AWRD/SYMV
  records δεν είναι ισοδύναμα με `VERIFIED_ACTIVE` διαγωνισμούς και χρειάζονται
  detail/status verification πριν παρουσιαστούν ως ενεργά έργα.
- Τα KIMDIS PROC documents έχουν structured artifact και UI preview/download,
  αλλά δεν έχουν ακόμη ενσωματωθεί στο SQLite search/evaluation pipeline όπως
  τα ESHIDIS documents.
- Το dashboard είναι πλέον η κύρια ροή λήψης εγγράφων: κάθε γραμμή έχει
  `Fetch` που αναγνωρίζει από τον κωδικό αν πρόκειται για ΕΣΗΔΗΣ ή ΚΗΜΔΗΣ και
  `ZIP` για όλα τα ήδη διαθέσιμα τοπικά έγγραφα της συγκεκριμένης γραμμής.
- Το `sources fetch-kimdis-open-proc` υποστηρίζει `--official-id`, ώστε το UI
  να μπορεί να κάνει fetch ενός συγκεκριμένου ΑΔΑΜ χωρίς να ξανατραβάει όλη
  τη λίστα open PROC.
- Προστέθηκε progress overlay στο UI με μήνυμα αναμονής κατά τα long-running
  fetch/download actions. Τα commands παραμένουν serialized με lock επειδή
  γράφουν κοινά runtime reports/indexes.
- Verification για την UI απλοποίηση:
  `.venv/bin/python -m tender_radar config validate` πέρασε για όλα τα config
  files.
- Targeted tests:
  `.venv/bin/python -m pytest tests/test_ui_server.py tests/test_kimdis_fetch.py`
  επέστρεψε `22 passed in 0.65s`.
- Full test suite:
  `.venv/bin/python -m pytest` επέστρεψε `69 passed in 1.67s`.
- Discovery depth defaults were raised for safer weekly use:
  - ESHIDIS active discovery default limit is now `100` rows instead of `25`.
  - KIMDIS expanded report default/UI depth is now `20` pages per record family
    instead of `5`.
  - The UI shows this depth next to the search controls.
- The UI discovery action now treats runtime `summary.errors` from the expanded
  report as warnings/failure instead of reporting a clean success when one
  source family failed silently.
- This improves recall but is not a mathematical guarantee. A no-miss weekly
  guarantee requires a persisted watermark/backfill gate that scans until it
  reaches the last successful run window, or until each source is exhausted.
- Verification for discovery-depth update:
  `.venv/bin/python -m tender_radar config validate` passed for all config
  files.
- Targeted tests:
  `.venv/bin/python -m pytest tests/test_ui_server.py tests/test_cli.py`
  returned `27 passed in 0.76s`.
- Full test suite:
  `.venv/bin/python -m pytest` returned `71 passed in 1.57s`.
- Long-running UI actions now use background jobs instead of holding the
  browser/server POST request open. Heavy endpoints return `202` with `job_id`
  and the UI polls `/api/jobs/{job_id}` every 5 seconds until completion or
  failure.
- The in-memory job registry covers discovery, per-row fetch, ESHIDIS detail
  fetch, download-all, KIMDIS fetch, analyze, search and evaluate actions.
  CLI commands remain serialized with `COMMAND_LOCK` because they write shared
  runtime reports and indexes.
- Verification for background jobs:
  `.venv/bin/python -m tender_radar config validate` passed for all config
  files.
- Targeted tests:
  `.venv/bin/python -m pytest tests/test_ui_server.py` returned
  `19 passed in 0.53s`.
- Full test suite:
  `.venv/bin/python -m pytest` returned `73 passed in 1.54s`.
- Dashboard rows are now clickable. Selecting a row updates the preview pane
  and highlights the selected row; row action buttons/links stop propagation
  so `Fetch`, `ZIP` and official links do not accidentally change selection.
- User confirmed a successful end-to-end UI workflow through the tunnel:
  a per-row `Fetch` completed successfully and the `ZIP` download was tested.
- Verification for clickable dashboard rows:
  `.venv/bin/python -m tender_radar config validate` passed for all config
  files.
- Targeted tests:
  `.venv/bin/python -m pytest tests/test_ui_server.py` returned
  `20 passed in 0.48s`.
- Full test suite:
  `.venv/bin/python -m pytest` returned `74 passed in 1.41s`.
- KIMDIS PROC document inspection now extracts candidate linked ESHIDIS
  numeric ids from explicit document context such as `Α/Α ΕΣΗΔΗΣ` or
  `Α/Α Συστήματος ΕΣΗΔΗΣ`. The extractor is conservative and does not treat
  unrelated 5-7 digit values as ESHIDIS ids without nearby official-id
  context.
- The KIMDIS document index and Markdown report preserve
  `linked_eshidis_ids`. The dashboard displays those ids in the row and in the
  KIMDIS preview pane.
- Dashboard KIMDIS row `Fetch` now runs a chained official-folder lookup:
  selected KIMDIS ADAM fetch first, then ESHIDIS `fetch-resource` and
  `download-attachment --all` for every linked ESHIDIS id found in the KIMDIS
  document/index. This remains candidate/provenance linking, not silent record
  merging.
- KIMDIS row ZIP archives now include the local KIMDIS document and any
  already-downloaded latest ESHIDIS files for linked ESHIDIS ids, using
  `ESHIDIS_<id>_` filename prefixes inside the archive.
- Verification for KIMDIS-to-ESHIDIS cross-reference:
  `.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_ui_server.py`
  returned `29 passed in 0.60s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 77 passed in 2.33s.
- `git diff --check`
- Result: no whitespace errors.
- Added runtime discovery watermark tracking in
  `src/tender_radar/discovery_watermark.py`. Discovery runs persist metadata
  to `work/derived/discovery_runs.json`, including started/completed time,
  mode, source family, ESHIDIS row limit, KIMDIS page depth, candidate ids,
  partial failures, source exhaustion flags and previous-window overlap.
- `sources expanded-report` now includes KIMDIS `source_pages` metadata with
  per-family page number, returned item count and page error, so backfill can
  distinguish "needs deeper scan" from a documented empty page.
- The UI discovery action supports two modes:
  - bounded: one pass at the selected ESHIDIS limit and current KIMDIS default
    depth;
  - backfill safety: repeated passes with increasing ESHIDIS/KIMDIS depth
    until the previous successful run window is reached or the configured
    maximum depth is hit.
- The dashboard shows the latest discovery watermark status, mode, depth and
  whether a deeper backfill is needed. Partial source failures are stored in
  the run record and exposed in the job result/dashboard payload.
- Verification for discovery watermark/backfill:
  `.venv/bin/python -m pytest tests/test_discovery_watermark.py tests/test_expanded_report.py tests/test_ui_server.py`
  returned `34 passed in 0.63s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 82 passed in 2.05s.
- `git diff --check`
- Result: no whitespace errors.
- Tightened KIMDIS-to-ESHIDIS id extraction for official documents that write
  the system acronym with punctuation, e.g. `Ε.Σ.Η.ΔΗ.Σ Α/Α :207024`, even
  when the numeric id is adjacent to a following URL. The extractor remains
  label-based and does not accept unrelated 5-7 digit values without nearby
  ESHIDIS/system context.
- Single-ADAM KIMDIS fetches now merge their updated document record into the
  existing KIMDIS document index instead of replacing the whole index. This
  keeps per-row refetches from hiding other already indexed KIMDIS rows.
- KIMDIS preview payloads now include `linked_eshidis_file_count`, and the UI
  tells the user whether linked ESHIDIS files are already available for ZIP or
  whether Fetch will attempt the official-folder download.
- Live verification for `26PROC019429074` extracted linked ESHIDIS id
  `207024`; the local SQLite/download state has 14 latest ESHIDIS files for
  `207024`.
- Verification for dotted ESHIDIS extraction and UI preview count:
  `.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_ui_server.py tests/test_cli.py`
  returned `43 passed in 1.06s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 84 passed in 1.77s.
- Added official ESHIDIS resource URL extraction for KIMDIS/declaration text:
  `pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/<id>` and
  short `resources/search/<id>` forms now produce linked ESHIDIS ids. This is
  constrained to the official resource path, not arbitrary numeric URLs.
- The linked ESHIDIS acronym normalizer now also covers the fully dotted form
  `Ε.Σ.Η.Δ.Η.Σ.`.
- Corpus check over `work/extracted_text/**/*.txt` found 10 files with
  official `resources/search/<id>` URLs; after the change the extractor found
  all URL ids in 10/10 files.
- KIMDIS document-index refresh after the URL extraction change:
  `.venv/bin/python -m tender_radar sources fetch-kimdis-open-proc --expanded-report work/reports/expanded_discovery_report.json --config config/sources.yml --download-dir work/download_audit/kimdis --text-dir work/extracted_text/kimdis --document-index work/derived/kimdis_open_proc_documents.json --report work/reports/kimdis_open_proc_fetch_report.json --markdown-report work/reports/kimdis_open_proc_fetch_report.md --limit 50 --timeout 30 --allow-insecure-tls`
- Result: 14 checked, 14 already present, 0 failed, 14 text extracted,
  14 document evidence found, 9 records with linked ESHIDIS ids.
- Newly visible examples include `26PROC019449985 -> 221627`,
  `26PROC019417347 -> 221691`, `26PROC019417050 -> 221684`, and
  `26PROC019367864 -> 221566, 221556`. Conflicting/multiple official URL ids
  are retained as separate linked candidates and are not silently corrected.
- Verification for resource URL extraction:
  `.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_ui_server.py tests/test_cli.py`
  returned `46 passed in 0.90s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 87 passed in 2.04s.
- Added guarded extraction for `Α/Α Διαγωνισμού <id>` when the nearby context
  proves the ESHIDIS/public works platform, such as `publicworks.eprocurement.gov.gr`,
  `eprocurement.gov.gr`, `ΕΣΗΔΗΣ` or `Ηλεκτρονικών Δημοσίων Συμβάσεων`.
  Unguarded `Α/Α Διαγωνισμού` numbers are ignored.
- Corpus check found one current KIMDIS extracted text with this pattern:
  `work/extracted_text/kimdis/26PROC019405070.txt`, now extracting `221624`.
- KIMDIS document-index refresh after the guarded competition-number change:
  `.venv/bin/python -m tender_radar sources fetch-kimdis-open-proc --expanded-report work/reports/expanded_discovery_report.json --config config/sources.yml --download-dir work/download_audit/kimdis --text-dir work/extracted_text/kimdis --document-index work/derived/kimdis_open_proc_documents.json --report work/reports/kimdis_open_proc_fetch_report.json --markdown-report work/reports/kimdis_open_proc_fetch_report.md --limit 50 --timeout 30 --allow-insecure-tls`
- Result: 14 checked, 14 already present, 0 failed, 14 text extracted,
  14 document evidence found, 10 records with linked ESHIDIS ids.
- New linked example: `26PROC019405070 -> 221624`.
- Verification for guarded competition-number extraction:
  `.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_ui_server.py tests/test_cli.py`
  returned `48 passed in 1.08s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 89 passed in 1.62s.
- First-page dashboard now supports explicit sort modes:
  - default `deadline_asc`, showing the nearest parseable submission deadline
    first;
  - `budget_desc`, showing the largest parsed budget first.
- The dashboard now hides rows with parseable deadlines before the current
  date. Rows with unknown/unparseable deadlines remain visible to avoid losing
  candidates because of source/parsing gaps.
- The first-page metrics no longer show the internal `γνωστά στο σύστημα`
  count. That value remains in the API summary for diagnostics, while the UI
  focuses on the operational list count and local-interest count.
- Runtime dashboard check:
  `dashboard_payload(scope='focus', sort='deadline_asc')` returned
  `total_known: 61`, `visible: 20`, `focus_matches: 20`, `expired_hidden: 2`;
  first rows were ordered by deadlines `21-07-2026`, `23-07-2026`,
  `23-07-2026`, `24-07-2026`.
- Runtime dashboard check:
  `dashboard_payload(scope='focus', sort='budget_desc')` returned the largest
  parsed budgets first, starting with `26PROC019429074` at `8.949.999,99 EUR`.
- Targeted verification:
  `.venv/bin/python -m pytest tests/test_ui_server.py tests/test_cli.py`
  returned `35 passed in 0.80s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 91 passed in 1.80s.
- KIMDIS linked ESHIDIS extraction now prefers explicit/context ids over
  conflicting URL-only ids in the same document. This fixed
  `26PROC019367864`, which now links only to `221566` instead of
  `221566, 221556`.
- ESHIDIS download import now falls back to unique normalized filename matching
  when exact attachment names differ only by Unicode/whitespace normalization.
  This fixed live downloads where the official listing used single spaces but
  browser-downloaded filenames contained doubled/tripled spaces.
- Live `221566` verification:
  `.venv/bin/python -m tender_radar sources fetch-resource 221566 --allow-insecure-tls`
  imported 25 attachment rows; `.venv/bin/python -m tender_radar sources download-attachment 221566 --all --limit 50 --allow-insecure-tls`
  downloaded 25/25 with 0 failures.
- `kimdis_document_preview_payload('26PROC019367864')` now reports
  `linked_eshidis_ids: ['221566']` and `linked_eshidis_file_count: 25`; the
  generated ZIP for `26PROC019367864` is about 257 MB.
- Live `221365` diagnostic:
  `fetch-resource 221365` reached the public resource URL but imported 0
  attachment rows. The captured ESHIDIS screenshot states that no electronic
  procedure exists for that system number or that the procedure is closed /
  limited to invited or preselected economic operators. This is not currently
  a public attachment-download failure.
- Latest source whitelist audit:
  `.venv/bin/python -m tender_radar sources audit-whitelist --allow-insecure-tls --timeout 8 --report work/reports/source_whitelist_audit_latest.json --markdown-report work/reports/source_whitelist_audit_latest.md`
  returned 36 total, 31 reachable, 1 failed, 0 adapter-required,
  4 templates, 0 failed-with-fallback and 0 unresolved blockers.
- The previously problematic e-Patras URLs are now reachable:
  `https://e-patras.gr/el/tenders` and
  `https://e-patras.gr/el/e-democracy/decisions/municipal-committee-decisions`.
  Reachability is proven; full municipal-page discovery/fetch adapters remain
  the next implementation gate.
- Targeted verification:
  `.venv/bin/python -m pytest tests/test_db.py tests/test_kimdis_fetch.py`
  returned `21 passed in 0.90s`.
- `.venv/bin/python -m tender_radar config validate`
- Result: all repository configs OK.
- `.venv/bin/python -m pytest`
- Result: 93 passed in 2.08s.

## Coverage

```yaml
sources_checked: 3
tenders_discovered: 15
candidate_detail_fetches_imported_this_task: 3
attachments_listed: 66
sqlite_tenders: 6
sqlite_latest_attachments: 66
attachments_downloaded: 17
documents_parsed: 17
documents_classified: 17
documents_with_text: 17
kimdis_open_proc_candidates: 12
kimdis_open_proc_attachments_fetched: 12
kimdis_open_proc_documents_with_text: 12
kimdis_open_proc_document_evidence_found: 12
kimdis_open_proc_document_index_rows: 12
kimdis_open_proc_text_artifacts: 12
kimdis_ui_preview_rows: 12
ambiguous_location_rules: 2
ambiguous_location_live_matches: 0
content_matches: 60
status_reports: 1
ui_dashboard_scope_focus_rows: 14
ui_dashboard_scope_all_rows: 32
ui_table_id_source_split: true
ui_kimdis_tools: true
ui_dashboard_row_fetch: true
ui_dashboard_zip_download: true
kimdis_fetch_single_official_id: true
eshidis_discovery_default_limit: 100
kimdis_discovery_default_pages_per_family: 20
ui_background_jobs: true
ui_job_poll_interval_seconds: 5
ui_clickable_preview_rows: true
ui_end_to_end_fetch_zip_confirmed_by_user: true
kimdis_extracts_linked_eshidis_ids: true
kimdis_extracts_dotted_eshidis_ids: true
kimdis_extracts_official_resource_url_eshidis_ids: true
kimdis_extracts_guarded_competition_eshidis_ids: true
ui_kimdis_fetch_chains_linked_eshidis: true
kimdis_zip_includes_linked_eshidis_downloads: true
ui_linked_eshidis_file_count: true
discovery_run_history_json: true
discovery_watermark_backfill: true
discovery_source_page_stats: true
source_whitelist_files: 2
source_whitelist_entries_checked: 36
source_whitelist_reachable: 29
source_whitelist_failed: 3
source_whitelist_adapter_required: 0
source_whitelist_templates: 4
source_whitelist_failed_with_fallback: 2
source_whitelist_unresolved_blockers: 0
expanded_report_total_candidates: 765
expanded_report_focus_candidates: 51
expanded_report_focus_proc: 13
expanded_report_focus_awrd: 20
expanded_report_focus_symv: 17
expanded_report_focus_open_proc: 12
expanded_report_focus_expired_proc: 0
expanded_report_focus_cancelled_proc: 1
expanded_report_focus_historical_awrd_symv: 37
deduplication_protocols: 2
discovered_active_candidates: 15
verified_active_matches: 0
unknown_statuses: 6
unexplained_failures: 0
focus_municipalities: 6
sample_linked_eshidis_207024_files: 14
official_resource_url_text_files_checked: 10
official_resource_url_text_files_extracted: 10
guarded_competition_text_files_checked: 1
guarded_competition_text_files_extracted: 1
kimdis_records_with_linked_eshidis_ids: 10
ui_dashboard_sort_deadline_asc: true
ui_dashboard_sort_budget_desc: true
ui_dashboard_hides_parseable_expired_rows: true
ui_dashboard_hides_known_total_metric: true
ui_dashboard_expired_hidden_rows: 2
kimdis_conflicting_url_ids_suppressed_when_context_id_exists: true
eshidis_download_import_normalized_filename_match: true
sample_eshidis_221566_attachment_rows: 25
sample_eshidis_221566_downloaded_files: 25
sample_eshidis_221365_public_attachment_rows: 0
source_whitelist_latest_entries_checked: 36
source_whitelist_latest_reachable: 31
source_whitelist_latest_failed: 1
source_whitelist_latest_unresolved_blockers: 0
epatras_tenders_reachable: true
epatras_committee_decisions_reachable: true
authority_adapters_configured: 2
authority_adapter_first_scope: patras
authority_adapter_supported_type: drupal_listing
authority_smoke_candidates: 2
authority_smoke_errors: 0
authority_ui_fetch_zip_enabled: true
authority_runtime_document_index: true
authority_ignore_list_enabled: true
sample_authority_row_downloaded_files: 9
sample_authority_zip_bytes: 9736178
authority_adapter_families: 5
authority_adapters_configured_latest: 24
authority_all_sources_smoke_candidates: 65
authority_all_sources_smoke_errors: 0
expanded_report_authority_candidates_latest: 108
dashboard_visible_focus_rows_latest: 128
```

## Next Gate

Extend the authority discovery adapter coverage to the remaining municipal,
regional, Diavgeia and TED sources from the double-checked audit, one source
family at a time, while keeping non-official-status records candidate-only.

## Latest Update - 2026-07-18

Implemented the first municipal/authority discovery adapter path:

- Added `src/tender_radar/sources/authority.py` with a public Drupal listing
  adapter for authority websites.
- Added `authority_adapters` configuration for:
  - `epatras_tenders`
  - `epatras_municipal_committee`
- Integrated authority candidates into `sources expanded-report`.
- Routed focus authority candidates into the dashboard merge path.
- Extracted explicit KIMDIS `26PROC...` and contextual ESHIDIS ids such as
  `Ε.Σ.Η.Δ.Η.Σ Α/Α 207024` where present.
- Kept authority rows as `AUTHORITY_DISCOVERY_CANDIDATE`; no record is promoted
  to `VERIFIED_ACTIVE`.

Verification:

```bash
.venv/bin/python -m tender_radar config validate
.venv/bin/python -m pytest tests/test_authority.py tests/test_expanded_report.py
.venv/bin/python -m tender_radar sources expanded-report --kimdis-pages 0 --authority-limit-per-source 2 --timeout 12 --report work/reports/authority_smoke.json --markdown-report work/reports/authority_smoke.md --allow-insecure-tls
.venv/bin/python -m pytest
```

Results:

```text
config validate: OK for all configured YAML files
targeted tests: 11 passed
authority smoke: 2 focus authority candidates, 0 errors
full test suite: 96 passed
```

## Latest Update - 2026-07-18 UI Authority Documents

Enabled the daily dashboard actions for municipal/authority rows:

- External row/source/document links open in a new tab.
- Authority rows with discovered attachment URLs now show `Fetch`.
- After fetch, authority rows expose local preview and ZIP from downloaded
  municipal files.
- Municipal downloads are stored under `work/download_audit/authority/` and
  indexed in `work/derived/authority_documents.json`.
- Added red `Δεν με ενδιαφέρει` row action backed by
  `work/derived/ignored_tenders.json`.

Verification:

```bash
.venv/bin/python -m tender_radar config validate
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_authority.py tests/test_expanded_report.py
.venv/bin/python -m pytest
.venv/bin/python -m tender_radar sources expanded-report --kimdis-pages 0 --authority-limit-per-source 4 --timeout 12 --report work/reports/authority_smoke.json --markdown-report work/reports/authority_smoke.md --allow-insecure-tls
.venv/bin/python -c "import json; from tender_radar.ui_server import run_selected_fetch, document_zip_bytes; r=run_selected_fetch('AUTHORITY:AUTH-d448a0b21a42080a'); print(json.dumps({'ok': r.get('ok'), 'downloaded': r.get('downloaded'), 'failed': r.get('failed'), 'failures': r.get('failures')}, ensure_ascii=False)); name, body = document_zip_bytes('AUTHORITY:AUTH-d448a0b21a42080a'); print(name, 0 if body is None else len(body))"
```

Results:

```text
config validate: OK for all configured YAML files
targeted tests: 39 passed
full test suite: 99 passed
authority smoke: 4 focus authority candidates, 0 errors
authority row AUTH-d448a0b21a42080a: downloaded 9, failed 0
authority ZIP: tender_AUTHORITY_AUTH-d448a0b21a42080a_documents.zip, 9736178 bytes
```

## Latest Update - 2026-07-18 Authority Source Expansion

Expanded the authority discovery layer beyond e-Patras.

Added adapter families:

- `wordpress_category`
- `wordpress_page_table`
- `html_listing`
- `diavgeia_api`
- `ted_api`

Configured source coverage now includes Ναυπακτία, Θέρμο, Αμφιλοχία,
Μεσολόγγι, Δωρίδα/Ευπάλιο, Πάτρα/ΔΕΥΑΠ, ΠΔΕ, ΠΣΤΕ, Διαύγεια org feeds and
TED active Greek notices. All authority records remain
`AUTHORITY_DISCOVERY_CANDIDATE` unless a separate official status check proves
active tender status.

Verification:

```bash
.venv/bin/python -m tender_radar config validate
.venv/bin/python -m pytest tests/test_authority.py tests/test_expanded_report.py tests/test_config.py
.venv/bin/python -m pytest
.venv/bin/python -m tender_radar sources expanded-report --kimdis-pages 0 --authority-limit-per-source 3 --timeout 8 --report work/reports/authority_all_sources_smoke.json --markdown-report work/reports/authority_all_sources_smoke.md --allow-insecure-tls
.venv/bin/python -m tender_radar sources expanded-report --allow-insecure-tls --kimdis-pages 20 --authority-limit-per-source 5 --timeout 12 --as-of-date 2026-07-18 --eshidis-candidates work/reports/eshidis_active_candidates.json --report work/reports/expanded_discovery_report.json --markdown-report work/reports/expanded_discovery_report.md
```

Results:

```text
config validate: OK for all configured YAML files
targeted tests: 16 passed
full test suite: 103 passed
authority all-sources smoke: 65 authority candidates, 0 errors
expanded report: 3123 total candidates, 385 focus candidates, 108 authority candidates, 0 errors
dashboard focus payload: 148 total_known, 128 visible, 1 expired_hidden, 2 ignored
```

## Latest Update - 2026-07-18 AI Discovery Triage Dry Run

Added an advisory OpenAI-backed triage command for the current dashboard
discovery rows:

```bash
.venv/bin/python -m tender_radar sources ai-triage-report --scope focus --batch-size 20 --timeout 90 --report work/reports/ai_triage_report.json --markdown-report work/reports/ai_triage_report.md
```

The command reads the existing dashboard payload, sends compact row summaries
and deterministic signals to the OpenAI Responses API using structured JSON
output, and writes JSON/Markdown reports under `work/reports/`. It does not
delete rows, mutate source records, merge records by title, or promote anything
to `VERIFIED_ACTIVE`.

Dry-run result against the current focus dashboard:

```text
dashboard input: 148 total_known, 128 visible, 1 expired_hidden, 2 ignored
AI triage rows: 128
KEEP_ACTIVE_TENDER: 17
REVIEW_TENDER_CANDIDATE: 18
EARLY_SIGNAL: 4
DROP_OUT_OF_SCOPE_SUPPLY_SERVICE: 39
DROP_ADMIN: 47
DROP_NOT_PUBLIC_WORKS: 3
kept/review/early total: 39
dropped total: 89
errors: 0
```

Verification:

```bash
.venv/bin/python -m pytest tests/test_ai_triage.py tests/test_cli.py tests/test_ui_server.py
.venv/bin/python -m pytest tests/test_ai_triage.py tests/test_cli.py
.venv/bin/python -m pytest
```

Results:

```text
targeted tests after initial implementation: 41 passed
targeted tests after structured-output hardening: 13 passed
full test suite: 106 passed
```

## Latest Update - 2026-07-18 Dashboard Triage Enforcement Preview

Applied the reviewed source/UI changes for a preview build:

- Removed noisy decision/context sources from active source config:
  - Δήμος Αμφιλοχίας - Αποφάσεις Δημάρχου
  - Δήμος Αμφιλοχίας - Αποφάσεις Δημοτικού Συμβουλίου
  - Δήμος Δωρίδος - Αποφάσεις Επιτροπών source link
  - Δήμος Πατρέων - Αποφάσεις Δημοτικής Επιτροπής
- `dashboard_payload` now loads cached `work/reports/ai_triage_report.json`
  when present.
- Rows classified by AI as `DROP_*` are hidden from the default daily view,
  while raw reports/provenance remain unchanged.
- Dashboard rows expose the AI decision pill for visible rows.
- When a KIMDIS/authority row has a linked or AI-hinted ESHIDIS id, the UI
  prefers the ESHIDIS resource link, Fetch identifier and ZIP identifier.
- All row/document links continue to open in a new browser tab/window.

Verification:

```bash
.venv/bin/python -m tender_radar config validate
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_config.py
.venv/bin/python -m pytest
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; import json; p=dashboard_payload(scope='focus'); print(json.dumps(p['summary'], ensure_ascii=False))"
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://cb7aaee390f414.lhr.life/
```

Results:

```text
config validate: OK for all configured YAML files
targeted tests: 30 passed
full test suite: 107 passed
dashboard focus summary: total_known 148, visible 39, focus_matches 128,
  expired_hidden 1, triage_hidden 89, ignored 2
preview tunnel: 200 text/html; charset=utf-8
```

### Hotfix - AI triage cache refresh after new discovery

After a new discovery run, the existing `ai_triage_report` cache could become
stale. The `sources ai-triage-report` command was also reading the already
triage-filtered dashboard payload, so newly discovered rows without AI
classification remained visible.

Fix:

- `dashboard_payload(..., apply_triage=False)` now exposes unfiltered active
  dashboard rows for internal report generation.
- `sources ai-triage-report` uses `apply_triage=False`, so AI refreshes classify
  the full current focus set.
- UI/dashboard calls keep `apply_triage=True` by default.

Current regenerated AI triage over the latest focus set:

```text
AI input rows: 217
KEEP_ACTIVE_TENDER: 14
REVIEW_TENDER_CANDIDATE: 32
EARLY_SIGNAL: 10
DROP_OUT_OF_SCOPE_SUPPLY_SERVICE: 67
DROP_ADMIN: 85
DROP_NOT_PUBLIC_WORKS: 9
kept/review/early total: 56
dropped total: 161
errors: 0
```

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_cli.py
.venv/bin/python -m tender_radar sources ai-triage-report --scope focus --batch-size 20 --timeout 90 --report work/reports/ai_triage_report.json --markdown-report work/reports/ai_triage_report.md
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; import json; p=dashboard_payload(scope='focus'); print(json.dumps(p['summary'], ensure_ascii=False))"
curl -s https://be7e9f6c65a95b.lhr.life/api/dashboard?scope=focus | .venv/bin/python -c "import sys,json; p=json.load(sys.stdin); print(p['summary'])"
.venv/bin/python -m pytest
```

Results:

```text
targeted tests: 39 passed
dashboard focus summary: total_known 224, visible 56, focus_matches 217,
  expired_hidden 1, triage_hidden 161, ignored 2
public tunnel dashboard summary: visible 56, triage_hidden 161
full test suite: 107 passed
```

### Hotfix - Fast source preflight before expensive discovery

The UI `Νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ` path now runs a cheap source
fingerprint preflight before starting the expensive ESHIDIS/KIMDIS/authority
discovery commands.

Implemented behavior:

- KIMDIS notice page 0 is checked through the public POST endpoint.
- WordPress, Diavgeia and TED sources are checked with one-record API probes.
- HTML/Drupal listing sources use `ETag`/`Last-Modified` when present, or a
  stable token from the first relevant listing links instead of hashing the
  whole dynamic page.
- The preflight runs source checks in parallel.
- If the current fingerprint matches the last saved baseline, the UI returns
  `SKIPPED_UNCHANGED` and does not execute the expensive discovery steps.
- Temporary preflight source failures are surfaced as warnings. If the
  overlapping successful sources are unchanged, the UI can still fast-skip
  with `SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS`.
- Only clean fingerprints are allowed to replace the complete baseline after a
  successful full discovery run, so partial source failures do not corrupt the
  last complete comparison point.

Live verification:

```bash
.venv/bin/python -c "from tender_radar.ui_server import quick_source_fingerprint, save_source_fingerprint; import time,json; t=time.time(); fp=quick_source_fingerprint(timeout_seconds=6); print(json.dumps({'seconds': round(time.time()-t, 2), 'ok': fp.get('ok'), 'sources': len(fp.get('sources', [])), 'errors': fp.get('errors')}, ensure_ascii=False)); save_source_fingerprint(fp)"
.venv/bin/python -c "from tender_radar.ui_server import run_discovery_search; import json,time; t=time.time(); r=run_discovery_search(limit=100); print(json.dumps({'seconds': round(time.time()-t, 2), 'ok': r.get('ok'), 'skipped': r.get('skipped'), 'skip_reason': r.get('skip_reason'), 'preflight_status': (r.get('source_preflight') or {}).get('status'), 'errors': (r.get('source_preflight') or {}).get('errors'), 'steps': len(r.get('steps') or []), 'visible': ((r.get('dashboard') or {}).get('summary') or {}).get('visible'), 'focus_matches': ((r.get('dashboard') or {}).get('summary') or {}).get('focus_matches')}, ensure_ascii=False))"
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_cli.py
.venv/bin/python -m pytest
```

Results:

```text
source fingerprint preflight: 2.54s, 19 reachable source probes, 3 temporary
  Diavgeia 503 errors
UI discovery search smoke: 4.24s, ok true, skipped true, steps 0,
  status SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS, visible 56, focus_matches 217
targeted tests: 42 passed
full test suite: 114 passed
```

### Hotfix - Selective refresh for changed non-ESHIDIS sources

The first source preflight fix was still coarse: when any source changed, the
UI fell back to the existing full discovery sequence. The expanded report path
now supports selective refresh for KIMDIS and authority/municipal/regional
sources.

Implemented behavior:

- `sources expanded-report` accepts repeatable `--kimdis-source-id` and
  `--authority-source-id` arguments.
- Skipped sources are not fetched again; their previous candidates are retained
  from `--previous-report`.
- Skipped sources are written in `source_pages` as `SKIPPED_UNCHANGED`.
- Dashboard discovery uses the preflight `changed_source_ids` to run only the
  changed KIMDIS/authority source families where possible.
- If a source fingerprint changed but the changed source cannot be identified,
  the UI falls back to full discovery instead of making an unsafe partial run.
- ESHIDIS browser active search is still treated as the special heavy source:
  selective non-ESHIDIS refresh reuses the existing ESHIDIS candidate report.
  Full/backfill discovery remains available when ESHIDIS must be refreshed.

Verification:

```bash
.venv/bin/python -c "from tender_radar.ui_server import discovery_search_steps; import json; steps=discovery_search_steps(limit=100, as_of_date='2026-07-18', source_preflight={'previous_hash':'x','changed_source_ids':['epatras_tenders']}, selective=True); print(json.dumps(steps, ensure_ascii=False, indent=2))"
.venv/bin/python -m tender_radar sources expanded-report --kimdis-source-id __none__ --authority-source-id __none__ --previous-report work/reports/expanded_discovery_report.json --report /tmp/expanded_selective_skip.json --markdown-report /tmp/expanded_selective_skip.md --timeout 1
.venv/bin/python -c "import json; p=json.load(open('/tmp/expanded_selective_skip.json', encoding='utf-8')); print(len([s for s in p['source_pages'] if s.get('status')=='SKIPPED_UNCHANGED']))"
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_authority.py tests/test_expanded_report.py tests/test_cli.py
.venv/bin/python -m pytest
```

Results:

```text
selective step builder for changed epatras_tenders: one expanded-report step,
  no ESHIDIS discover-active step, KIMDIS set to __none__,
  authority-source-id epatras_tenders
selective skipped expanded report: 24 SKIPPED_UNCHANGED source page entries
targeted tests: 58 passed
full test suite: 111 passed
```

### Hotfix - Prefer canonical ESHIDIS rows over linked KIMDIS duplicates

Dashboard duplicate suppression now hides secondary KIMDIS/authority rows when
they explicitly link to an ESHIDIS id that already exists as a canonical
ESHIDIS dashboard row. This is deterministic and does not rely on AI triage.

Implemented behavior:

- KIMDIS rows with `linked_eshidis_ids` are suppressed when the linked ESHIDIS
  id is already present as an active/canonical ESHIDIS row.
- AI-proposed `eshidis_id_candidates` are also considered for duplicate
  suppression after AI triage is attached.
- SQLite-only ESHIDIS metadata without a deadline does not suppress KIMDIS
  rows, so local document-preview tests and stale metadata do not hide the
  only actionable row.
- Dashboard summary now includes `duplicate_hidden`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_cli.py
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; import json; p=dashboard_payload(scope='focus'); print(json.dumps(p['summary'], ensure_ascii=False)); print([(r.get('display_id'), r.get('source_label'), r.get('title')) for r in p['tenders'][:8]])"
.venv/bin/python -m pytest
```

Results:

```text
targeted tests: 44 passed
dashboard focus summary: total_known 255, visible 47, focus_matches 208,
  expired_hidden 2, duplicate_hidden 9, triage_hidden 161, ignored 2
full test suite: 112 passed
```

### Hotfix - Context-first ESHIDIS id extraction from tender documents

The KIMDIS document inspection extractor now treats 6-digit ESHIDIS ids as the
primary modern pattern and removed broad 7-digit matching. It keeps a narrow
5-digit legacy fallback only when the text explicitly says ESHIDIS.

Implemented behavior:

- Official `pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/<id>`
  links are parsed as 6-digit ESHIDIS ids.
- Article `2.2` style declaration text remains covered through the official
  URL and guarded `Α/Α Διαγωνισμού <id>` patterns when nearby context contains
  ESHIDIS/eprocurement wording.
- `ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ` documents now allow `Α/Α ΣΥΣΤΗΜΑΤΟΣ: <6 digits>`
  to be treated as a linked ESHIDIS id.
- Plain `Α/Α Συστήματος` without economic-offer or ESHIDIS context is rejected.
- The uploaded sample economic offer form extracted `216631`; the public
  ESHIDIS resource URL returned HTTP 200 and showed the same system number,
  title and Δήμος Δωρίδος authority.

Verification:

```bash
.venv/bin/python -m pytest tests/test_kimdis_fetch.py tests/test_authority.py
.venv/bin/python -c "from pathlib import Path; from pypdf import PdfReader; from tender_radar.sources.kimdis_fetch import extract_eshidis_ids_from_text; p=Path('/tmp/codex-remote-attachments/019f70df-c848-7e11-8bea-04f60ee7ca6d/19109841-FF1E-42E4-B9B2-E62BF040A88A/1-ΕΝΤΥΠΟ-ΟΙΚΟΝΟΜΙΚΗΣ-ΠΡΟΣΦΟΡΑΣ-ΕΙΣΗΔΗΣ.pdf'); text='\n'.join(page.extract_text() or '' for page in PdfReader(str(p)).pages); print(extract_eshidis_ids_from_text(p.name, text))"
curl -L -s -o /tmp/eshidis_216631.html -w '%{http_code} %{content_type} %{time_total}\n' 'https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/216631'
.venv/bin/python -m pytest
```

Results:

```text
targeted tests: 26 passed
uploaded economic offer form: ['216631']
official ESHIDIS resource 216631: 200 text/html;charset=UTF-8
full test suite: 115 passed
```

### Hotfix - Hide authority landing pages and surface deterministic ESHIDIS hints

The PDE `Έργα & Δράσεις` row was a generic authority landing/navigation page
captured from `https://pde.gov.gr/el/erga-drasis/`. It is not a tender
publication and is now excluded before it reaches the main dashboard.

Implemented behavior:

- The authority HTML adapter skips known non-tender landing candidates such as
  `/erga-drasis/` / `Έργα & Δράσεις`.
- The dashboard defensively hides the same landing rows from cached expanded
  reports, so old reports do not keep the noise visible.
- Authority rows now run the existing deterministic ESHIDIS id extractor over
  title, source/detail URLs, attachment URLs and row text. Any found ids are
  exposed as `linked_eshidis_ids` and shown in the dashboard pills.
- The AI triage prompt now explicitly instructs the model to look for article
  `2.2`, official `resources/search/<id>` URLs, guarded `Α/Α Διαγωνισμού`,
  `ΟΠΣ ΕΣΗΔΗΣ`, `Α/Α ΕΣΗΔΗΣ`, and `ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ` /
  `Α/Α ΣΥΣΤΗΜΑΤΟΣ` contexts.
- AI ESHIDIS hints are normalized to 5- or 6-digit ids only; broad 7-digit
  hints are rejected.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ai_triage.py tests/test_authority.py tests/test_ui_server.py
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; p=dashboard_payload(scope='focus', apply_triage=False); rows=p['tenders']; linked=[(r.get('row_key'), r.get('source_label'), r.get('title'), r.get('linked_eshidis_ids')) for r in rows if r.get('linked_eshidis_ids')]; print(p['summary']); print('linked_visible', len(linked)); print(linked[:15])"
.venv/bin/python -c "from tender_radar.ai_triage import build_ai_triage_report; rows=[{'row_key':'test','source_label':'Φορέας','title':'Διακήρυξη έργου Α/Α ΕΣΗΔΗΣ 221744','authority_name':'Δήμος'}]; r=build_ai_triage_report(rows,batch_size=1,timeout_seconds=15); print(r['summary']); print(r['rows'][0]['ai'])"
.venv/bin/python -m pytest
```

Results:

```text
targeted tests: 48 passed
dashboard unfiltered focus summary: total_known 253, visible 206,
  duplicate_hidden 9; Έργα & Δράσεις no longer present
deterministic linked_visible: 2
single-row AI smoke: KEEP_ACTIVE_TENDER with eshidis_id_candidates ['221744']
full test suite: 119 passed
```

AI full-list refresh note:

- A full `sources ai-triage-report` run over the current focus list was
  attempted twice (`batch-size 20` and `batch-size 5`) but both stayed blocked
  inside an OpenAI HTTPS response until interrupted.
- The single-row AI smoke succeeded, so credentials and prompt work. The
  production AI enrichment path needs batch-level progress/partial writes and
  a dedicated title/document enrichment job before it should be used for long
  runs from the UI.

### Hotfix - Search button source preflight counts all configured sources

The UI `Νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ` path now preflights every configured
entry in `config/sources.yml`, not only the previous KIMDIS notice plus
authority subset.

Implemented behavior:

- Source preflight builds its worklist from both `global_sources` and
  `authority_adapters`.
- URL templates are counted as configured sources but marked
  `REQUIRES_IDENTIFIER` and not called without a known official id.
- The API response now includes `source_count` with configured, attempted,
  reached, template and error totals.
- Selective refresh is used only for changed source ids that the UI can
  refresh selectively. If a non-selective global source changes, the UI falls
  back to full discovery instead of pretending the selective path covered it.

Live preflight on `2026-07-18`:

```text
configured_total: 31
attempted_total: 27
reached_total: 24
template_total: 4
error_total: 3
```

Errors in that live run:

```text
diavgeia_messolonghi: HTTP Error 503: Service Temporarily Unavailable
diavgeia_pste: HTTP Error 503: Service Temporarily Unavailable
eshidis_active_search: The read operation timed out
```

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py
.venv/bin/python -c "from tender_radar.ui_server import quick_source_fingerprint; import json; p=quick_source_fingerprint(timeout_seconds=8); print(json.dumps({'ok': p['ok'], 'source_count': p.get('source_count'), 'errors': p.get('errors', [])[:10]}, ensure_ascii=False, indent=2)); print('sources_len', len(p.get('sources', [])))"
.venv/bin/python -m pytest
```

Results:

```text
targeted tests: 39 passed
live source preflight: 31 configured, 27 attempted, 24 reached, 4 templates,
  3 errors
full test suite: 122 passed
```

### Hotfix - Delta refresh instead of full discovery for changed ESHIDIS/KIMDIS/source rows

The UI discovery orchestration no longer treats `eshidis_active_search` as a
non-selective source that forces a full discovery whenever its fingerprint
changes.

Implemented behavior:

- `eshidis_active_search`, `khmdhs_notice`, `khmdhs_auction`,
  `khmdhs_contract` and configured authority adapter ids are delta-capable for
  UI discovery orchestration.
- If only `eshidis_active_search` changes, the UI runs only
  `sources discover-active` and then `sources expanded-report` with
  `--previous-report`, `--kimdis-source-id __none__` and
  `--authority-source-id __none__`.
- If only one KIMDIS family changes, the UI runs only `sources expanded-report`
  for that KIMDIS family and retains unchanged ESHIDIS/authority/KIMDIS rows
  from the previous report.
- If only one authority source changes, the existing selective authority path
  remains in place.
- Full discovery is still used only when there is no previous baseline, no
  identified changed source ids, backfill is explicitly requested, or a changed
  source id is outside the delta-capable set.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py
.venv/bin/python -m pytest
```

Results:

```text
targeted tests: 40 passed
full test suite: 123 passed
```

### Step 2 - Deterministic public-works gate for discovery rows

The search/discovery report now separates daily public-works candidates from
non-public-works rows before the dashboard renders them. Raw candidates remain
in `all_candidates` with provenance; filtered focus rows are stored separately
with a reason.

Implemented behavior:

- ESHIDIS active-search rows are kept as official public-works discovery rows.
- KIMDIS and authority rows get a `public_works_gate` with decision, reason,
  matched public-works terms, tender terms and drop terms.
- Rows with clear administrative/news/personnel/election/meeting wording and
  no tender wording are marked `DROP_ADMIN` and excluded from the daily focus
  lists.
- Rows with clear supply/service wording and no infrastructure/public-works
  signal are marked `DROP_OUT_OF_SCOPE_SUPPLY_SERVICE` and excluded.
- Rows with public-works terms plus tender/procurement/document evidence are
  kept as `KEEP_PUBLIC_WORKS_CANDIDATE`.
- The expanded report now includes `focus_filtered_non_public_works` and the
  summary count `focus_filtered_non_public_works`.
- The dashboard defensively applies the same gate to cached authority/KIMDIS
  rows that predate this metadata, so a `SKIPPED_UNCHANGED` preflight does not
  resurrect old non-public-works rows.

Verification:

```bash
.venv/bin/python -m pytest tests/test_expanded_report.py tests/test_ui_server.py
.venv/bin/python -m pytest
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; p=dashboard_payload(scope='focus', apply_triage=False); print({'visible': p['summary'].get('visible'), 'total_known': p['summary'].get('total_known'), 'focus': p['summary'].get('focus')}); print([(r.get('row_key'), r.get('source_label'), (r.get('public_works_gate') or {}).get('decision')) for r in p.get('tenders', [])[:10]])"
```

Results:

```text
targeted tests: 50 passed
full test suite: 125 passed
cached dashboard smoke: visible 79, total_known 126
```

### Steps 3 and 4 - Official source labeling and authority document ESHIDIS extraction

The dashboard now treats only ESHIDIS rows as official tender rows and uses
KIMDIS/authority rows as candidates until they produce an explicit ESHIDIS
cross-reference.

Implemented behavior:

- Every dashboard row gets `official_status` and `official_status_label`.
- ESHIDIS rows show `OFFICIAL_ESHIDIS` / `Επίσημο ΕΣΗΔΗΣ`.
- KIMDIS/authority rows with extracted linked ESHIDIS ids show
  `LINKED_TO_ESHIDIS` / `Σύνδεση με ΕΣΗΔΗΣ`.
- KIMDIS/authority rows without extracted ESHIDIS ids show
  `CANDIDATE_NO_ESHIDIS_ID` / `Δεν βρέθηκε ακόμα ΕΣΗΔΗΣ`.
- Authority-row Fetch now downloads all known public attachment URLs, analyzes
  supported documents, writes extracted text under
  `work/extracted_text/authority/`, extracts ESHIDIS ids from filename, title,
  source URL, attachment URL and document text, and stores
  `linked_eshidis_ids` in `work/derived/authority_documents.json`.
- If authority Fetch finds linked ESHIDIS ids, it immediately runs the official
  ESHIDIS detail fetch and full official attachment download for those ids.
- Authority preview now shows either a linked ESHIDIS message or an explicit
  note that no ESHIDIS id was found after checking downloaded documents.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py tests/test_kimdis_fetch.py
.venv/bin/python -m pytest
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; p=dashboard_payload(scope='focus', apply_triage=False); print({'visible': p['summary'].get('visible'), 'total_known': p['summary'].get('total_known')}); print([(r.get('row_key'), r.get('source_label'), r.get('official_status_label'), r.get('linked_eshidis_ids')) for r in p.get('tenders', [])[:10]])"
```

Results:

```text
targeted tests: 61 passed
full test suite: 126 passed
cached dashboard smoke: visible 79, total_known 126
```

### Step 5 - Linked ESHIDIS canonical promotion

The UI discovery pipeline now promotes explicit linked ESHIDIS ids into the
official path instead of leaving KIMDIS/authority duplicates as primary
dashboard rows.

Implemented behavior:

- After `sources expanded-report`, the UI scans dashboard rows for
  `linked_eshidis_ids` that do not yet exist as canonical ESHIDIS rows.
- Missing linked ids trigger the same official `sources fetch-resource` and
  `sources download-attachment --all --limit 50` steps used by the Fetch
  button.
- KIMDIS/authority rows are hidden from the main dashboard only when their
  linked id is present as a real ESHIDIS dashboard row from the current
  ESHIDIS report or SQLite metadata with a deadline.
- SQLite-only stale ESHIDIS rows without a deadline do not hide KIMDIS rows,
  so unresolved candidates remain visible with provenance.
- Linked ESHIDIS ids that were already attempted but still did not become
  canonical are recorded in `work/derived/linked_eshidis_fetch_attempts.json`
  and skipped on the next bounded search to avoid repeated slow retries.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m pytest
.venv/bin/python -c "import json; from tender_radar.ui_server import run_linked_eshidis_enrichment, dashboard_payload; results, summary=run_linked_eshidis_enrichment(); print(json.dumps({'steps': [(r.get('name'), r.get('returncode')) for r in results], 'summary': summary, 'dashboard': dashboard_payload(scope='focus')['summary']}, ensure_ascii=False))"
.venv/bin/python -c "import json; from tender_radar.ui_server import run_linked_eshidis_enrichment; results, summary=run_linked_eshidis_enrichment(); print(json.dumps({'steps': [(r.get('name'), r.get('returncode')) for r in results], 'summary': summary}, ensure_ascii=False))"
```

Results:

```text
targeted UI tests: 44 passed
full test suite: 128 passed
linked ESHIDIS smoke #1: attempted 221365, fetch_detail passed, download_files failed because no attachment rows were selected; enriched 0, failed 1
linked ESHIDIS smoke #2: attempted 0, skipped_previously_attempted 221365
cached dashboard after smoke: total_known 126, visible 35, duplicate_hidden 9, triage_hidden 44
```

### Municipality attachment URL encoding fix

The Dorida/Efpalio authority row exposed all tender attachments, but the
authority downloader failed before fetching most PDFs because Greek filenames
were passed to `urllib` without percent-encoding.

Implemented behavior:

- Authority document downloads now encode the URL path before making the HTTP
  request while keeping human-readable local filenames.
- Authority dashboard rows now merge `linked_eshidis_ids` found in previously
  downloaded/analyzed authority documents back into the dashboard row.
- The Efpalio row
  `AUTHORITY:AUTH-6e565827798444b6` now downloads 6/6 municipal PDFs and
  extracts ESHIDIS id `217922` from both the summary declaration
  (`ΑΡ. ΕΣΗΔΗΣ: 217922`) and the economic offer form
  (`Α/Α ΣΥΣΤΗΜΑΤΟΣ: 217922`).
- Official ESHIDIS fetch/download for `217922` succeeded. Because the official
  row is not active as of the current date, the Efpalio authority candidate is
  no longer visible in the active dashboard after canonical duplicate/expiry
  filtering.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m pytest
.venv/bin/python -c "import json; from tender_radar.ui_server import run_authority_fetch, authority_document_preview_payload; r=run_authority_fetch('AUTHORITY:AUTH-6e565827798444b6'); p=authority_document_preview_payload('AUTHORITY:AUTH-6e565827798444b6'); print(json.dumps({'fetch': {'ok': r.get('ok'), 'downloaded': r.get('downloaded'), 'failed': r.get('failed'), 'linked_eshidis_ids': r.get('linked_eshidis_ids')}, 'preview': {'linked_eshidis_ids': p.get('linked_eshidis_ids')}}, ensure_ascii=False))"
```

Results:

```text
targeted UI tests: 46 passed
full test suite: 130 passed
Efpalio authority fetch: ok true, downloaded 6, failed 0, linked_eshidis_ids ['217922']
official ESHIDIS 217922 fetch/download: both steps returned 0
```

### Discovery preflight no-full-depth guard

The daily UI search now avoids expensive full discovery when cheap source
fingerprints are degraded by temporary source failures but no discovery-relevant
successful source has changed.

Implemented behavior:

- `changed_source_ids` now ignores `url_template` entries and generic source
  audit landing pages that are not daily discovery adapters.
- The baseline comparison now uses the latest saved fingerprint, including a
  degraded fingerprint with source warnings, instead of falling back only to an
  older complete baseline.
- A skipped preflight with warnings saves the current fingerprint so the same
  degraded state does not repeatedly trigger work.
- Daily discovery-relevant changes are limited to `eshidis_active_search`,
  KIMDIS API families and configured authority adapters.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m pytest
.venv/bin/python -c "import json; from tender_radar.ui_server import run_discovery_search; r=run_discovery_search(limit=100, backfill=False); print(json.dumps({'ok': r.get('ok'), 'skipped': r.get('skipped'), 'steps': [(s.get('name'), s.get('returncode')) for s in r.get('steps', [])], 'preflight_status': (r.get('source_preflight') or {}).get('status')}, ensure_ascii=False))"
```

Results:

```text
targeted UI tests: 49 passed
full test suite: 133 passed
bounded run smoke: ok true, skipped true, steps [], preflight_status SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS
```

### Persistent runtime state foundation

The DigitalOcean runtime now has a SQLite-backed state foundation for the
daily poll/deploy workflow.

Implemented behavior:

- Added `source_state` for per-source fingerprint, last checked timestamp,
  last changed timestamp, status, errors and metadata.
- Added `source_runs` for per-run source audit history with status, changed
  flag, item count, error and metadata.
- Added `tender_dismissals` for permanent "Δεν με ενδιαφέρει" row ignores.
- Added `notification_log` for future email alert de-duplication per row,
  channel and recipient.
- Added DB helpers for source state upsert/read, source run audit, tender
  dismissal and notification sent guards.
- The UI dismissal path now writes to SQLite while still reading the legacy
  `work/derived/ignored_tenders.json` file so existing ignored rows are not
  lost during migration.

Verification:

```bash
.venv/bin/python -m pytest tests/test_db.py tests/test_ui_server.py::test_dismiss_tender_hides_row_from_dashboard
.venv/bin/python -m pytest
```

Results:

```text
targeted DB/UI tests: 10 passed
full test suite: 142 passed
```

### UI version badge and SQLite-backed source preflight

Implemented behavior:

- Bumped the application version from `0.1.0` to `0.1.1`.
- The UI header now shows the live version badge as `v0.1.1` next to
  `Δημόσια έργα`.
- Discovery preflight now persists every source fingerprint check to SQLite:
  `source_state` stores the latest state per source and `source_runs` stores
  each poll attempt.
- Preflight comparisons now read the previous per-source fingerprint from
  SQLite first. The legacy `work/derived/source_fingerprints.json` remains as
  compatibility output/fallback.
- Skip/change decisions are source-specific. A failing source is recorded as
  an error for that source and does not by itself force global full-depth
  discovery.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_discovery_preflight_uses_sqlite_source_state_before_json tests/test_ui_server.py::test_discovery_skips_when_source_fingerprint_is_unchanged tests/test_ui_server.py::test_discovery_skips_when_successful_sources_are_unchanged_with_preflight_errors
.venv/bin/python -m pytest
.venv/bin/python -c "import json, sqlite3; from tender_radar.ui_server import discovery_change_preflight, runtime_db_path; r=discovery_change_preflight(); db=runtime_db_path(); con=sqlite3.connect(db); source_count=con.execute('select count(*) from source_state').fetchone()[0]; run_count=con.execute('select count(*) from source_runs').fetchone()[0]; con.close(); print(json.dumps({'status': r.get('status'), 'skip': r.get('skip'), 'changed_source_ids': r.get('changed_source_ids'), 'error_count': len(r.get('errors') or []), 'source_state_rows': source_count, 'source_run_rows': run_count}, ensure_ascii=False))"
```

Results:

```text
targeted UI/preflight tests: 4 passed
full test suite: 144 passed
first local preflight smoke: status CHANGED_OR_NO_BASELINE, skip false, changed_source_ids ['diavgeia_messolonghi', 'diavgeia_pde', 'khmdhs_auction', 'khmdhs_contract', 'khmdhs_notice'], error_count 4, source_state_rows 31, source_run_rows 31
second local preflight smoke: status CHANGED_OR_NO_BASELINE, skip false, changed_source_ids ['diavgeia_patras', 'diavgeia_thermo'], error_count 4, source_state_rows 31, source_run_rows 62
```

### Source polling audit visible in UI

Implemented behavior:

- Added `/api/source-polling`, backed by SQLite `source_state`, to expose the
  latest configured source status without running any network discovery.
- The first UI screen now includes a compact source audit table with source
  name/id, adapter, status, last checked timestamp, error and whether the
  source has a selective-refresh path.
- The UI summary separates total changed/error counts from
  `selective_changed_total` and `selective_error_total`, so generic/non-daily
  sources do not look like mandatory full-discovery triggers.
- Runtime view refreshes now update both the dashboard and the source audit
  after discovery, fetch, AI triage/enrichment and permanent dismiss actions.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_exposes_source_polling_audit tests/test_ui_server.py::test_source_polling_payload_reads_sqlite_state_and_config tests/test_ui_server.py::test_discovery_preflight_uses_sqlite_source_state_before_json
.venv/bin/python -m pytest
.venv/bin/python -c "import json; from tender_radar.ui_server import source_polling_payload; p=source_polling_payload(); print(json.dumps(p['summary'], ensure_ascii=False))"
```

Results:

```text
targeted UI/source polling tests: 3 passed
full test suite: 146 passed
local source polling smoke: configured_total 31, tracked_total 31, selective_capable_total 25, changed_total 4, selective_changed_total 2, error_total 4, selective_error_total 4, requires_identifier_total 4, never_checked_total 0
```

### UI v0.1.2 and email alert de-duplication

Implemented behavior:

- Bumped the application version from `0.1.1` to `0.1.2` so live UI changes
  are visibly identifiable.
- Added `/api/email-alerts`, which consumes the current dashboard rows instead
  of running discovery.
- Email alert de-duplication uses SQLite `notification_log` per row key,
  channel and recipient.
- The email body includes clickable official URLs plus title, source label,
  authority, budget and deadline.
- The first UI screen now has `Email νέων έργων`; real sending requires SMTP
  runtime configuration in env or `.env.local`. Dry-run does not mutate
  `notification_log`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_ui_exposes_email_alert_button tests/test_ui_server.py::test_email_alerts_payload_skips_rows_already_sent tests/test_ui_server.py::test_ui_exposes_source_polling_audit
.venv/bin/python -m pytest
.venv/bin/python -c "import json; from tender_radar.ui_server import email_alerts_payload; p=email_alerts_payload(recipient='smoke@example.test', dry_run=True); print(json.dumps({k:p[k] for k in ['candidate_rows','new_count','skipped_already_sent','sent','dry_run']}, ensure_ascii=False)); print((p['new_rows'][0] if p['new_rows'] else {}).get('official_url'))"
```

Results:

```text
targeted UI/email tests: 4 passed
full test suite: 148 passed
local email dry-run smoke: candidate_rows 29, new_count 29, skipped_already_sent 0, sent 0, dry_run true
first dry-run link: https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/221566
```

### UI v0.1.4 scheduled poll and alert

Implemented behavior:

- Bumped the application version from `0.1.2` to `0.1.4` so the live header
  identifies the scheduler build.
- Added `tender-radar runtime scheduled-run`, a bounded runtime entry point for
  the droplet scheduler.
- The scheduled command runs the daily sequence only: bounded discovery with
  `backfill=False`, AI triage, linked-candidate enrichment and email alerts.
- Scheduled AI triage is incremental: it reuses existing row-key decisions and
  sends only untriaged rows to OpenAI. When every current row already has AI
  triage, the scheduled job skips the OpenAI stage.
- The scheduled command writes JSON and Markdown audit artifacts with source
  counts, changed sources, skipped sources, source errors, stage summaries and
  email new/skipped/sent counts.
- Added systemd unit/timer templates under `deploy/systemd/` for a 6-hour
  droplet schedule guarded by `flock`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_scheduled_poll_and_alert_writes_audit_reports tests/test_cli.py::CliTests::test_runtime_help_lists_scheduled_run tests/test_cli.py::CliTests::test_scheduled_run_parser_supports_dry_run
.venv/bin/python -m pytest
.venv/bin/python -m tender_radar runtime scheduled-run --dry-run --recipient smoke@example.test --limit 1 --ai-batch-size 5 --enrichment-limit 1 --report work/reports/scheduled_poll_alert_smoke.json --markdown-report work/reports/scheduled_poll_alert_smoke.md
```

Results:

```text
targeted scheduler/version tests: 4 passed
full test suite: 151 passed
local scheduled dry-run smoke: ok true, dry_run true, changed_source_ids ['diavgeia_pde', 'diavgeia_pste'], source_errors 4, email candidate_rows 27, new_count 27, sent 0
```

Follow-up fix verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_scheduled_poll_and_alert_writes_audit_reports tests/test_ui_server.py::test_scheduled_poll_skips_ai_when_all_rows_already_triaged tests/test_cli.py::CliTests::test_runtime_help_lists_scheduled_run tests/test_cli.py::CliTests::test_scheduled_run_parser_supports_dry_run
.venv/bin/python -m pytest
```

Results:

```text
targeted incremental scheduler tests: 4 passed
full test suite: 152 passed
```

Droplet verification after deploy:

```bash
gh run watch 29664227866 --repo CryptoLearningLab/dimoprasies --exit-status
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && git rev-parse --short HEAD && systemctl is-active tender-radar-ui.service'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'curl -s http://127.0.0.1:8765/ | grep -o "v0.1.4" | head -1'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && .venv/bin/python -m tender_radar runtime scheduled-run --dry-run --recipient smoke@example.test --limit 1 --ai-batch-size 5 --enrichment-limit 1 --report work/reports/scheduled_poll_alert_droplet_v014.json --markdown-report work/reports/scheduled_poll_alert_droplet_v014.md'
```

Results:

```text
GitHub Actions deploy 29664227866: success
droplet HEAD: 413f5a6
tender-radar-ui.service: active
live UI version: v0.1.4
tender-radar-scheduled.timer: loaded but disabled/inactive because SMTP env keys are missing
droplet scheduled dry-run: ok true, elapsed about 33s, AI triage skipped true, changed_source_ids ['deyap_prokurhxeis', 'diavgeia_deya_nafpaktias', 'eshidis_active_search'], source_errors 3, email candidate_rows 34, new_count 34, sent 0
```

Limitations observed:

- The droplet `.env.local` contains `OPENAI_API_KEY`, but does not yet contain
  `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` or
  an alert recipient key. Therefore the timer was installed but left disabled
  to avoid scheduled send failures.
- The scheduled path no longer reruns OpenAI for already-triaged rows, but
  `eshidis_active_search` can still trigger bounded ESHIDIS discovery. That is
  now a 30-second-class operation in the observed smoke, not a 5-minute AI
  rerun, and should be stabilized further with a better ESHIDIS watermark.

### UI v0.1.5 ESHIDIS scheduler fingerprint stabilization

Implemented behavior:

- Bumped the application version from `0.1.4` to `0.1.5`.
- `eshidis_active_search` source preflight now uses the latest
  `work/reports/eshidis_active_candidates.json` candidate snapshot as its cheap
  fingerprint when that report exists.
- The fingerprint is built from stable candidate evidence: top ESHIDIS ids,
  titles, authorities, deadlines/publication dates and candidate count.
- This prevents transient browser page noise, session ids or timeout behavior
  from forcing bounded ESHIDIS discovery when no new active candidate snapshot
  has been produced.
- After a successful bounded discovery pass, the stored source fingerprint is
  refreshed from the updated candidate report so the next scheduled run can
  skip cleanly.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_eshidis_active_preflight_uses_cached_candidate_report tests/test_ui_server.py::test_discovery_preflight_uses_sqlite_source_state_before_json tests/test_ui_server.py::test_discovery_selectively_refreshes_eshidis_only_when_eshidis_source_changed tests/test_ui_server.py::test_scheduled_poll_skips_ai_when_all_rows_already_triaged
.venv/bin/python -m pytest
```

Results:

```text
targeted ESHIDIS scheduler tests: 4 passed
full test suite: 153 passed
```

### UI v0.1.6 transient source error state preservation

Implemented behavior:

- Bumped the application version from `0.1.5` to `0.1.6`.
- When a source temporarily fails during preflight, the SQLite source state now
  preserves the previous successful fingerprint and metadata token/date.
- The source is still marked `ERROR` with the latest error message, but the
  error no longer erases the last good fingerprint and causes a false changed
  trigger on the next recovery.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_source_error_preserves_previous_successful_fingerprint tests/test_ui_server.py::test_eshidis_active_preflight_uses_cached_candidate_report tests/test_ui_server.py::test_discovery_preflight_skips_when_only_failed_sources_are_degraded
.venv/bin/python -m pytest
```

Results:

```text
targeted transient-error tests: 3 passed
full test suite: 154 passed
```

### UI v0.1.7 scheduled skip orchestration

Implemented behavior:

- Bumped the application version from `0.1.6` to `0.1.7`.
- When scheduled discovery is skipped because source preflight found no real
  content changes, the scheduled job now also skips linked-candidate enrichment.
- Email dry-run/send still consumes the current dashboard state, and
  incremental AI triage remains allowed to fill missing triage rows without
  forcing document enrichment.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_scheduled_poll_skips_enrichment_when_discovery_skipped tests/test_ui_server.py::test_source_error_preserves_previous_successful_fingerprint tests/test_ui_server.py::test_eshidis_active_preflight_uses_cached_candidate_report
.venv/bin/python -m pytest
```

Results:

```text
targeted scheduled-skip tests: 3 passed
full test suite: 155 passed
```

Droplet verification after deploy:

```bash
gh run watch 29664747542 --repo CryptoLearningLab/dimoprasies --exit-status
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && git rev-parse --short HEAD && systemctl is-active tender-radar-ui.service'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'curl -s http://127.0.0.1:8765/ | grep -o "v0.1.7" | head -1'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && /usr/bin/time -f "ELAPSED %e" .venv/bin/python -m tender_radar runtime scheduled-run --dry-run --recipient smoke@example.test --limit 1 --ai-batch-size 5 --enrichment-limit 1 --report work/reports/scheduled_poll_alert_droplet_v017_a.json --markdown-report work/reports/scheduled_poll_alert_droplet_v017_a.md'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && /usr/bin/time -f "ELAPSED %e" .venv/bin/python -m tender_radar runtime scheduled-run --dry-run --recipient smoke@example.test --limit 1 --ai-batch-size 5 --enrichment-limit 1 --report work/reports/scheduled_poll_alert_droplet_v017_b.json --markdown-report work/reports/scheduled_poll_alert_droplet_v017_b.md'
```

Results:

```text
GitHub Actions deploy 29664747542: success
droplet HEAD: 597259c
tender-radar-ui.service: active
live UI version: v0.1.7
first v0.1.7 scheduled dry-run: ok true, elapsed 4.88s, discovery skipped true, AI triage skipped true, enrichment skipped true, email sent 0 dry_run true
second v0.1.7 scheduled dry-run: ok true, elapsed 4.29s, discovery skipped true, AI triage skipped true, enrichment skipped true, email sent 0 dry_run true
```

Remaining limitation:

- The systemd timer remains installed but disabled because outbound email env
  keys are not configured on the droplet yet.

### Production email env and 6-hour timer enabled

Implemented behavior:

- Configured the droplet `.env.local` with SMTP/email keys without recording
  secret values in repository docs.
- Ran a controlled scheduled dry-run after SMTP configuration.
- Ran one controlled real-send scheduled smoke to the owner recipient.
- Confirmed SQLite `notification_log` moved from `0` to `33` rows only after
  the successful real send.
- Enabled `tender-radar-scheduled.timer`.
- The immediate systemd timer tick after enabling did not re-send old rows:
  it reported `new_count: 0`, `skipped_already_sent: 33`, `sent: 0`.

Verification:

```bash
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && .venv/bin/python -c "from tender_radar.ui_server import smtp_config, email_alert_recipient; smtp_config(); assert email_alert_recipient(); print(\"smtp env present\")"'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && /usr/bin/time -f "ELAPSED %e" .venv/bin/python -m tender_radar runtime scheduled-run --dry-run --limit 1 --ai-batch-size 5 --enrichment-limit 1 --report work/reports/scheduled_poll_alert_email_dryrun.json --markdown-report work/reports/scheduled_poll_alert_email_dryrun.md'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && /usr/bin/time -f "ELAPSED %e" .venv/bin/python -m tender_radar runtime scheduled-run --limit 1 --ai-batch-size 5 --enrichment-limit 1 --report work/reports/scheduled_poll_alert_email_real.json --markdown-report work/reports/scheduled_poll_alert_email_real.md'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'systemctl enable --now tender-radar-scheduled.timer'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'systemctl is-enabled tender-radar-scheduled.timer && systemctl is-active tender-radar-scheduled.timer'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'systemctl list-timers tender-radar-scheduled.timer --no-pager --all'
```

Results:

```text
SMTP_HOST: present
SMTP_PORT: present
SMTP_USERNAME: present
SMTP_PASSWORD: present
EMAIL_FROM: present
ALERT_EMAIL_TO: present
notification_log before real send: 0
email dry-run: ok true, recipient configured, candidate_rows 33, new_count 33, sent 0, elapsed 5.03s
real send: ok true, sent 33, elapsed 6.54s
notification_log after real send: 33
tender-radar-scheduled.timer: enabled, active
next scheduled run: Sun 2026-07-19 05:31:42 UTC
latest scheduled report: work/reports/scheduled_poll_alert_latest.json
latest scheduled tick: ok true, dry_run false, sent 0, new_count 0, skipped_already_sent 33, discovery skipped true
```

### Stable HTTPS access on droplet

Implemented behavior:

- Installed Caddy on the DigitalOcean droplet.
- Added a reverse proxy for:
  `https://165.227.143.152.sslip.io/`
- Changed `tender-radar-ui.service` with a systemd drop-in so the Python UI
  listens only on `127.0.0.1:8765`.
- Opened firewall ports `80/tcp` and `443/tcp`.
- Removed the old public firewall allowance for `8765/tcp`.
- Caddy obtained a public Let's Encrypt certificate successfully.

Verification:

```bash
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'caddy validate --config /etc/caddy/Caddyfile'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'curl -I --max-time 20 http://165.227.143.152.sslip.io/'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'curl -s -L --max-time 30 https://165.227.143.152.sslip.io/ | grep -o "Tender Radar" | head -1'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && curl -s -L --max-time 30 https://165.227.143.152.sslip.io/api/dashboard?scope=focus | .venv/bin/python -c "import sys,json; p=json.load(sys.stdin); print(p.get(\"summary\",{}).get(\"visible\"), p.get(\"summary\",{}).get(\"total_known\"))"'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'systemctl is-active tender-radar-ui.service && systemctl is-active caddy.service && systemctl is-enabled tender-radar-scheduled.timer && systemctl is-active tender-radar-scheduled.timer'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'ss -ltnp | grep -E ":(80|443|8765)" || true'
```

Results:

```text
Caddy config: valid
HTTP: 308 redirect to https://165.227.143.152.sslip.io/
HTTPS page smoke: Tender Radar
HTTPS dashboard smoke: 33 visible, 89 total known
tender-radar-ui.service: active
caddy.service: active
tender-radar-scheduled.timer: enabled, active
listeners: 80/443 public via Caddy, 8765 localhost-only
certificate: obtained successfully by Caddy/Let's Encrypt
```

### UI v0.1.8 authority document provenance and re-download skip

Implemented behavior:

- Bumped the application version from `0.1.7` to `0.1.8`.
- Added SQLite `source_documents` runtime state for non-ESHIDIS source
  documents.
- The table records:
  - source row key,
  - source URL,
  - document URL,
  - local path,
  - size,
  - SHA-256,
  - fetched timestamp,
  - fetch error,
  - source signature,
  - metadata such as linked ESHIDIS ids and extracted text path.
- Authority/municipal/regional row fetches now check SQLite before downloading
  a document again. If the same row/document URL has the same source signature,
  a local file exists and SHA-256 is present, the document is reused and counted
  as skipped.
- Fetch failures are also persisted in `source_documents` with `fetch_error`
  instead of being hidden.
- ESHIDIS official attachment downloads already use the existing
  `attachments` table and skip behavior. KIMDIS retains its existing document
  index/skip behavior; future work may migrate it into `source_documents`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_db.py::test_source_documents_track_fetch_provenance tests/test_ui_server.py::test_authority_fetch_reuses_unchanged_source_document
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_db.py::test_source_documents_track_fetch_provenance tests/test_ui_server.py::test_authority_fetch_reuses_unchanged_source_document
.venv/bin/python -m pytest
gh run watch 29665833050 --repo CryptoLearningLab/dimoprasies --exit-status
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && .venv/bin/python - <<\"PY\"
from tender_radar.ui_server import run_authority_fetch
import json
row_key=\"AUTHORITY:AUTH-f36d0588e7c7b729\"
first=run_authority_fetch(row_key)
second=run_authority_fetch(row_key)
print(json.dumps({
  \"first\": {\"ok\": first.get(\"ok\"), \"downloaded\": first.get(\"downloaded\"), \"skipped\": first.get(\"skipped\"), \"failed\": first.get(\"failed\")},
  \"second\": {\"ok\": second.get(\"ok\"), \"downloaded\": second.get(\"downloaded\"), \"skipped\": second.get(\"skipped\"), \"failed\": second.get(\"failed\")},
}, ensure_ascii=False))
PY'
```

Results:

```text
targeted document fetcher tests: 2 passed
targeted version/provenance tests: 3 passed
full test suite: 157 passed
GitHub Actions deploy 29665833050: success
droplet HEAD: 5bff693
live UI version: v0.1.8
droplet authority smoke first run: ok true, downloaded 5, skipped 0, failed 0
droplet authority smoke second run: ok true, downloaded 0, skipped 5, failed 0
SQLite source_documents smoke row: 5 rows, 5 with local path and SHA-256
tender-radar-ui.service: active
caddy.service: active
tender-radar-scheduled.timer: enabled, active
```

### UI v0.1.9 scheduled auto document fetch before alerts

Implemented behavior:

- Bumped the application version from `0.1.8` to `0.1.9`.
- Added `run_auto_document_fetch()` as the scheduled document-collection stage.
- `tender-radar runtime scheduled-run` now runs automatic document fetch after
  incremental AI triage and before email alerts.
- If source discovery is skipped as unchanged, scheduled auto-fetch is also
  skipped so the cron does not process old unresolved candidates. When
  discovery actually runs, auto-fetch uses the existing candidate-enrichment
  attempt ledger and SQLite `source_documents` provenance to avoid repeated
  work for unchanged rows.
- Scheduled auto-fetch has a default time budget of `20` seconds. When the
  budget is reached, it stops before starting the next row, records
  `stopped_by_time_budget` and still lets the scheduled run proceed to email
  and audit-report writing.
- Auto-fetch target failures are recorded as scheduled-run warnings, not
  fatal run errors, so one bad external document fetch does not prevent email
  alerts or audit output.
- The scheduled JSON audit exposes both `auto_document_fetch` and the legacy
  `enrichment` key for backward-compatible report readers.
- Manual row `Fetch` remains available as a retry/admin action, not as the
  required normal path before OCR/email.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_scheduled_poll_skips_auto_document_fetch_when_discovery_skipped tests/test_ui_server.py::test_candidate_enrichment_uses_selected_fetch_and_records_attempts tests/test_ui_server.py::test_authority_fetch_reuses_unchanged_source_document
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_scheduled_poll_skips_auto_document_fetch_when_discovery_skipped
.venv/bin/python -m py_compile src/tender_radar/__init__.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_ui_server.py::test_auto_document_fetch_stops_before_next_target_when_budget_expires tests/test_ui_server.py::test_scheduled_poll_and_alert_writes_audit_reports
.venv/bin/python -m pytest tests/test_ui_server.py::test_scheduled_poll_treats_auto_document_fetch_failure_as_warning tests/test_ui_server.py::test_scheduled_poll_and_alert_writes_audit_reports tests/test_ui_server.py::test_auto_document_fetch_stops_before_next_target_when_budget_expires
.venv/bin/python -m pytest
gh run watch 29666867413 --repo CryptoLearningLab/dimoprasies --exit-status
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && git rev-parse --short HEAD && curl -s -L --max-time 30 https://165.227.143.152.sslip.io/ | grep -o "v0.1.9" | head -1 && systemctl is-active tender-radar-ui.service && systemctl is-active caddy.service && systemctl is-enabled tender-radar-scheduled.timer && systemctl is-active tender-radar-scheduled.timer'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && /usr/bin/time -f "ELAPSED %e" .venv/bin/python -m tender_radar runtime scheduled-run --dry-run --limit 1 --ai-batch-size 5 --enrichment-limit 10 --report work/reports/scheduled_poll_alert_auto_fetch_v019_final.json --markdown-report work/reports/scheduled_poll_alert_auto_fetch_v019_final.md'
```

Results:

```text
targeted auto-fetch/fetcher tests: 3 passed
targeted version/scheduler tests: 2 passed
targeted time-budget/report tests: 2 passed
targeted warning/report tests: 3 passed
full test suite: 159 passed
GitHub Actions deploy 29666867413: success
droplet HEAD: 66a7396
live UI version: v0.1.9
tender-radar-ui.service: active
caddy.service: active
tender-radar-scheduled.timer: enabled, active
scheduled dry-run: ok true, discovery skipped true, AI triage skipped true, auto_document_fetch skipped true, errors 0, warnings 0, elapsed 6.94s
```

### UI v0.1.10 admin audit and restore panel

Implemented behavior:

- Bumped the application version from `0.1.9` to `0.1.10`.
- Added an `Admin panel` tab inside the main UI, not a separate `/admin` route.
- Added admin login support with email one-time code sent to the configured
  admin/alert email and password fallback through `TENDER_RADAR_ADMIN_PASSWORD`
  or `ADMIN_PASSWORD`.
- Added SQLite `triage_overrides` runtime state for manual AI triage
  corrections.
- Added dismissal restore support by deleting from SQLite
  `tender_dismissals` and the legacy ignored-tenders JSON bridge.
- The admin audit reports AI-hidden rows, `Δεν με ενδιαφέρει` dismissals,
  duplicate-hidden rows, expired-hidden rows and source errors.
- The only restore action in this gate is `Επαναφορά`, scoped to AI-hidden
  rows and mistakenly dismissed rows. Duplicate and expired rows are audit-only.
- Restore asks for a reason and stores a `FORCE_KEEP` override.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_exposes_admin_panel tests/test_ui_server.py::test_admin_email_code_flow tests/test_ui_server.py::test_admin_restore_ai_hidden_row_forces_keep tests/test_ui_server.py::test_admin_restore_dismissed_row_removes_ignore tests/test_db.py::test_tender_dismissal_can_be_removed tests/test_db.py::test_triage_overrides_are_keyed_by_row
.venv/bin/python -m py_compile src/tender_radar/__init__.py src/tender_radar/db.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest
```

Results:

```text
targeted admin/db tests: 6 passed
full test suite: 165 passed
```

### UI v0.1.11 OCR fallback for weak PDF text extraction

Implemented behavior:

- Bumped the application version from `0.1.10` to `0.1.11`.
- Added deterministic OCR fallback for PDF document analysis:
  - OCR is not attempted when embedded PDF text extraction returns enough text;
  - OCR is attempted when extraction fails, returns no text, has no extractor,
    or returns very short text under the configured threshold;
  - OCR uses local system tools `pdftoppm` and `tesseract` when available;
  - OCR is bounded to the first 3 pages in this gate to avoid slow full-file
    scans during normal cron/document processing;
  - missing OCR tools are recorded as `OCR_TOOL_MISSING` instead of failing the
    app.
- Added OCR provenance fields to document analysis outputs:
  - `ocr_status`
  - `ocr_error`
- Added `ocr_status` and `ocr_error` columns to SQLite `documents`, with
  migration support for existing databases.
- Updated document-analysis Markdown reports to show the OCR status per file.
- Kept existing non-PDF behavior unchanged. Originals remain untouched; OCR
  temporary page images are created under a temporary directory and removed
  after processing.

Verification:

```bash
.venv/bin/python -m pytest tests/test_documents.py::test_pdf_text_extraction_does_not_run_ocr_for_strong_text tests/test_documents.py::test_pdf_weak_text_attempts_ocr_when_available tests/test_documents.py::test_pdf_weak_text_records_missing_ocr_tools tests/test_documents.py::test_render_markdown_report_includes_types_and_files
.venv/bin/python -m py_compile src/tender_radar/documents.py src/tender_radar/db.py src/tender_radar/cli.py src/tender_radar/__init__.py
.venv/bin/python -m pytest
```

Results:

```text
targeted OCR/document tests: 4 passed
py_compile: passed
full test suite: 168 passed
```

Live droplet deployment/smoke:

```bash
gh run watch 29668034720 --repo CryptoLearningLab/dimoprasies --exit-status
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && git rev-parse --short HEAD && curl -s -L --max-time 30 https://165.227.143.152.sslip.io/ | grep -o "v0.1.11" | head -1 && systemctl is-active tender-radar-ui.service && systemctl is-active caddy.service && systemctl is-enabled tender-radar-scheduled.timer && systemctl is-active tender-radar-scheduled.timer'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'apt-get update && apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-ell'
ssh -o StrictHostKeyChecking=no codex-crisp-hawk-a759 'cd /root/workspace/dimoprasies && .venv/bin/python -c "import shutil; from tender_radar.documents import needs_ocr; print({\"pdftoppm\": bool(shutil.which(\"pdftoppm\")), \"tesseract\": bool(shutil.which(\"tesseract\")), \"needs_ocr_empty\": needs_ocr(\"NO_TEXT_FOUND\", None), \"needs_ocr_short\": needs_ocr(\"TEXT_EXTRACTED\", \"λίγο\")})"'
```

Results:

```text
GitHub Actions deploy 29668034720: success
droplet HEAD: 839dfde
live UI version: v0.1.11
tender-radar-ui.service: active
caddy.service: active
tender-radar-scheduled.timer: enabled, active
droplet OCR tools: pdftoppm true, tesseract true
needs_ocr_empty: true
needs_ocr_short: true
existing PDF smoke:
  4. ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ.pdf -> TEXT_EXTRACTED_WITH_OCR, OCR_TEXT_EXTRACTED, 3528 chars
  ΤΟΙΧΟΙ (signed).pdf -> TEXT_EXTRACTED_WITH_OCR, OCR_TEXT_EXTRACTED, 4109 chars
  11.1 41.4 ΕΓΚΡΙΤΙΚΗ ΑΠΟΦΑΣΗ ΜΕΛΕΤΗΣ...pdf -> TEXT_EXTRACTED, NOT_NEEDED, 5927 chars
```

### UI v0.1.12 admin password setup and user invitations

Implemented behavior:

- Bumped the application version from `0.1.11` to `0.1.12`.
- Added SQLite admin/user identity tables:
  - `admin_users`
  - `admin_invites`
- Added password setup links:
  - owner/admin can request a password setup link for the configured admin
    email;
  - admin can send invitation links to additional `user` or `admin` accounts;
  - invite/reset tokens are stored only as SHA-256 hashes and expire after
    24 hours;
  - user passwords are stored as PBKDF2-SHA256 hashes with random salts, never
    as plaintext.
- Added `/password-setup?token=...` UI route and setup form.
- Added Admin panel invite controls and a users audit table.
- Existing one-time email code login remains available for the owner/admin.
- Runtime env password remains only as fallback/emergency admin auth.
- Non-admin `user` accounts can be created but cannot access admin audit,
  restore or invite actions.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_exposes_admin_panel tests/test_ui_server.py::test_admin_email_code_flow tests/test_ui_server.py::test_admin_password_setup_hashes_password tests/test_ui_server.py::test_admin_invite_user_creates_user_role
.venv/bin/python -m py_compile src/tender_radar/db.py src/tender_radar/ui_server.py src/tender_radar/__init__.py
.venv/bin/python -m pytest
```

Results:

```text
targeted admin auth tests: 4 passed
py_compile: passed
full test suite: 170 passed
```

### UI v0.1.13 private login and mobile dashboard cleanup

Implemented behavior:

- Bumped the application version from `0.1.12` to `0.1.13`.
- Added a private first screen with email/password login before the app shell
  is shown.
- Added `/api/auth/status`, `/api/auth/login` and `/api/auth/logout` for
  normal UI sessions.
- Dashboard/action APIs now reject unauthenticated requests with HTTP 401
  instead of relying only on hidden frontend content.
- Existing SQLite invite/password users can log into the main app; only
  `admin` role sessions can see admin audit, restore and invite controls.
- Removed the old admin login form from the Admin panel. The panel now focuses
  on invitations, audit/restore and logout.
- Added mobile card labels for tender rows so the main tender list can be read
  on phone screens without horizontal table dragging.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_ui_exposes_admin_panel tests/test_ui_server.py::test_front_page_uses_authenticated_app_shell tests/test_ui_server.py::test_tender_table_has_mobile_card_labels tests/test_ui_server.py::test_admin_password_setup_hashes_password tests/test_ui_server.py::test_admin_invite_user_creates_user_role
.venv/bin/python -m pytest
.venv/bin/python -c "from http.server import ThreadingHTTPServer; import threading, json, http.client; from tender_radar.ui_server import TenderRadarHandler; server=ThreadingHTTPServer(('127.0.0.1',0), TenderRadarHandler); port=server.server_address[1]; threading.Thread(target=server.serve_forever, daemon=True).start(); conn=http.client.HTTPConnection('127.0.0.1', port, timeout=5); conn.request('GET','/'); html=conn.getresponse().read().decode('utf-8'); conn.request('GET','/api/auth/status'); auth=json.loads(conn.getresponse().read().decode('utf-8')); conn.request('GET','/api/dashboard?scope=focus'); resp=conn.getresponse(); body=resp.read().decode('utf-8'); print({'loginScreen':'id=\"loginScreen\"' in html,'version':'v0.1.13' in html,'auth':auth.get('authenticated'),'dashboard_status':resp.status,'dashboard_body':body[:120]}); server.shutdown()"
```

Results:

```text
py_compile: passed
targeted UI/auth/mobile tests: 6 passed
full test suite: 172 passed
in-process UI smoke: loginScreen true, version true, unauthenticated auth false,
  dashboard_status 401, dashboard_body "Login required."
```

### UI v0.1.14 fetched/OCR evidence feeds AI triage

Implemented behavior:

- Bumped the application version from `0.1.13` to `0.1.14`.
- Incremental AI triage now enriches pending rows with fetched document
  evidence before calling OpenAI.
- Document evidence is assembled from SQLite `source_documents` and the
  existing KIMDIS/authority document indexes.
- Each evidence item includes filename, document type, extraction status,
  OCR status/error, fetch error, deterministic linked ESHIDIS ids and bounded
  text snippets.
- Snippet selection prioritizes the first page, article `2.2`, ESHIDIS
  wording, `pwgopendata`/`publicworks` URLs, `actSearchErgwn`, `Α/Α
  Διαγωνισμού`, `Α/Α Συστήματος` and economic-offer form context.
- Deterministic ESHIDIS ids extracted from OCR/text evidence are merged onto
  the row before AI classification.
- Candidate enrichment now prefers an AI/OCR-discovered linked ESHIDIS id over
  refetching a municipal/authority/KIMDIS source row. That means the next
  enrichment step hits `resources/search/{id}` directly when the id is known.
- Already-triaged unchanged rows still skip OpenAI.
- Cached AI rows now carry a `triage_signature` over the current dashboard row
  and fetched/OCR document evidence. A cached decision is reused only when the
  signature still matches, so newly fetched or newly OCR-extracted documents
  force one fresh AI pass instead of preserving stale hidden/kept results.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py src/tender_radar/ai_triage.py
.venv/bin/python -m pytest tests/test_ui_server.py::test_scheduled_poll_skips_ai_when_all_rows_already_triaged tests/test_ui_server.py::test_incremental_ai_triage_rechecks_stale_cached_rows tests/test_ui_server.py::test_incremental_ai_triage_includes_fetched_ocr_document_text tests/test_ui_server.py::test_candidate_enrichment_uses_ai_eshidis_id_before_refetching_authority tests/test_ai_triage.py
.venv/bin/python -m pytest
```

Results:

```text
py_compile: passed
targeted AI/document triage tests: 8 passed
full test suite after signature cache invalidation: 175 passed
```

### Production smoke fetched/OCR AI classifier

Implemented behavior after live smoke:

- The AI triage cache signature now includes `AI_TRIAGE_PROMPT_VERSION`.
  Prompt changes therefore invalidate cached decisions once, while unchanged
  rows still skip OpenAI on the next identical run.
- Tightened the AI prompt from observed live false-keeps: technical-consultant
  services, standalone studies, direct assignments (`Απευθείας Ανάθεση` /
  άρθρο 118), supplies even with installation/commissioning, vehicle/machinery
  repairs, transport services, Μη.Μ.Ε.Δ. drawings, signed contracts, awards
  and administrative approvals must not be parked as
  `REVIEW_TENDER_CANDIDATE` when they are clearly excluded.
- Dropped AI rows now have their `eshidis_id_candidates` cleared during
  normalization, so a hallucinated or irrelevant ESHIDIS hint on a rejected
  supply/service/admin row cannot feed downstream official linking.
- The cache/prompt version was advanced to
  `2026-07-19-strict-non-works-v2` after the dropped-hint guard so production
  reports are regenerated once with the safer normalization.

Production smoke before prompt tightening:

```text
droplet commit: 8079a1b
live package version: 0.1.14
tender-radar-ui.service: active
caddy.service: active
HTTPS /: 200 text/html; charset=utf-8
HTTPS /api/dashboard without login: 401 application/json; charset=utf-8
incremental AI triage first run: ok true, skipped false, pending_rows 77,
  retained_rows 0, elapsed 74.07s
incremental AI triage second unchanged run: ok true, skipped true,
  skip_reason NO_PENDING_AI_TRIAGE_ROWS, elapsed 3.48s
AI report: total 77, kept 26, dropped 51, with_document_evidence 10,
  with_linked_eshidis 11
candidate enrichment smoke: attempted 4 of 5 targets within 30s budget,
  skipped_previously_attempted 9, stopped_by_time_budget true,
  one failed ESHIDIS lookup for candidate 470011
```

Observed concrete classifier gaps from the live report:

- `AUTH-371a3333be4025ca`: technical-consultant services for Patras school
  energy-upgrade tender documents was retained as `REVIEW_TENDER_CANDIDATE`.
- `AUTH-57f303393ebd0ce3`: technical/scientific consultant services for
  tender-document drafting was retained as `REVIEW_TENDER_CANDIDATE`.
- `AUTH-78c18fb8b4c656e7`: direct-assignment article 118 fire-protection
  systems repair/maintenance was retained as `REVIEW_TENDER_CANDIDATE`.
- `AUTH-af4e5f93b5324404`: supply/installation/commissioning telecontrol
  procurement was retained as `REVIEW_TENDER_CANDIDATE` and produced an
  ESHIDIS candidate `470011`, which failed the official fetch smoke.

Verification after prompt tightening:

```bash
.venv/bin/python -m py_compile src/tender_radar/ai_triage.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_ai_triage.py tests/test_ui_server.py::test_scheduled_poll_skips_ai_when_all_rows_already_triaged tests/test_ui_server.py::test_incremental_ai_triage_rechecks_stale_cached_rows tests/test_ui_server.py::test_ai_triage_signature_includes_prompt_version tests/test_ui_server.py::test_incremental_ai_triage_includes_fetched_ocr_document_text tests/test_ui_server.py::test_candidate_enrichment_uses_ai_eshidis_id_before_refetching_authority
.venv/bin/python -m pytest tests/test_ai_triage.py tests/test_ui_server.py::test_ai_triage_signature_includes_prompt_version tests/test_ui_server.py::test_incremental_ai_triage_includes_fetched_ocr_document_text
.venv/bin/python -m pytest
```

Results:

```text
py_compile: passed
targeted prompt/signature/OCR tests: 10 passed
targeted dropped-hint/signature/OCR tests: 8 passed
full test suite after dropped-hint guard: 178 passed
full test suite after prompt/cache v2 bump: 178 passed
```

Final production smoke after deploy:

```text
droplet commit: ab0d497
AI_TRIAGE_PROMPT_VERSION: 2026-07-19-strict-non-works-v2
v2 incremental AI triage first run: ok true, skipped false, pending_rows 77,
  retained_rows 0, elapsed 80.69s
v2 incremental AI triage second unchanged run: ok true, skipped true,
  skip_reason NO_PENDING_AI_TRIAGE_ROWS, elapsed 3.22s
v2 AI report: total 77, kept 17, dropped 60, with_document_evidence 12,
  kept_with_linked_eshidis 9, dropped_rows_with_eshidis_hints 0
candidate enrichment smoke after v2: ok true, targets 1, attempted 1,
  skipped_previously_attempted 6, failed 0, stopped_by_time_budget false,
  elapsed 7.81s
```

No full discovery was run during the production smoke. The smoke used
`run_incremental_ai_triage` and `run_candidate_enrichment` directly against
the existing dashboard/report state on the droplet.

### UI v0.1.15 verified ESHIDIS link persistence

- Bumped the application version from `0.1.14` to `0.1.15`.
- Added SQLite table `verified_tender_links` for official cross-source links
  from KIMDIS/authority rows to verified ESHIDIS ids. Each persisted link keeps
  source row key, source identifier, source label/url, target ESHIDIS id,
  source signature, verification timestamp and evidence JSON.
- Candidate enrichment now stores verified links only after the official
  ESHIDIS fetch succeeds. Linked ids from AI/OCR/document extraction remain
  hints until this verification step passes.
- Dashboard duplicate suppression now uses persisted verified links, not title
  similarity and not unverified linked-id hints. When an official ESHIDIS row
  exists for a verified link, the non-ESHIDIS row is hidden as a verified
  duplicate and the official row retains provenance through
  `verified_source_links`.
- Non-ESHIDIS rows without verified links remain visible with
  `NO_VERIFIED_ESHIDIS_LINK` style status, so review candidates are not lost.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/db.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_db.py tests/test_ui_server.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; p=dashboard_payload(scope='focus'); print(p['summary']); print('visible', len(p['tenders'])); print('non_verified_review', sum(1 for r in p['tenders'] if r.get('source_label')!='ΕΣΗΔΗΣ' and r.get('verified_eshidis_link_status')=='NO_VERIFIED_ESHIDIS_LINK'))"
```

Results:

```text
py_compile: passed
focused DB/UI tests: 97 passed
full test suite: 183 passed
local dashboard smoke without full discovery:
  total_known 95
  visible 37
  duplicate_hidden 0
  non_verified_review 29
droplet smoke after deploy:
  deployed v0.1.15
  package version 0.1.15
  HTTPS / 200 text/html; charset=utf-8
  HTTPS /api/dashboard without login 401 application/json; charset=utf-8
  total_known 109
  visible 29
  verified_links 0
  duplicate_hidden 0
  non_verified_review 22
```

The local smoke did not run discovery or enrichment. It used the existing
runtime reports/database; because no verified links had been persisted in that
local DB yet, no rows were replaced and 29 non-ESHIDIS review candidates
remained visible.

The droplet smoke also avoided full discovery and used only current runtime
state. The live database had no persisted verified links at deploy time, so no
rows were replaced and 22 non-ESHIDIS visible review candidates remained.

### UI v0.1.16 strong linked duplicate suppression

- Bumped the application version from `0.1.15` to `0.1.16`.
- Added a bounded duplicate suppression exception for obvious cross-source
  duplicates that have an explicit linked ESHIDIS id already present as an
  official ESHIDIS row and at least two matching fields among title, deadline,
  budget and authority.
- Such rows are hidden as `STRONG_LINKED_ESHIDIS_DUPLICATE`. This is not
  title-only deduplication and it does not persist a verified link unless the
  official fetch verification gate has run.
- The example class covered by this gate is a KIMDIS row such as
  `26PROC019367864` linked to official ESHIDIS `221566` with the same title,
  deadline and budget.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; p=dashboard_payload(scope='focus'); print(p['summary']); print('visible', len(p['tenders'])); print('strong_duplicates', p['summary'].get('duplicate_hidden')); print('non_verified_review', sum(1 for r in p['tenders'] if r.get('source_label')!='ΕΣΗΔΗΣ' and r.get('verified_eshidis_link_status')=='NO_VERIFIED_ESHIDIS_LINK'))"
```

Results:

```text
py_compile: passed
focused UI tests: 85 passed
full test suite: 184 passed
local dashboard smoke without full discovery:
  total_known 95
  visible 29
  duplicate_hidden 8
  non_verified_review 21
```

### UI v0.1.17 linked ESHIDIS deadline filtering

- Bumped the application version from `0.1.16` to `0.1.17`.
- Fixed expired authority/KIMDIS rows that had no direct `ΛΗΞΗ` value but did
  have a linked official ESHIDIS id. The dashboard now uses the linked
  official ESHIDIS deadline for active/expired filtering when the source row
  lacks its own deadline.
- This addresses rows such as authority candidates linked to ESHIDIS `217922`
  and `216631`, whose official deadlines are `16-02-2026 15:00:00` and
  `19-01-2026 15:00:00` respectively.
- This was a dashboard active-filter issue, not an AI prompt issue.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; p=dashboard_payload(scope='focus'); print(p['summary']); print('visible', len(p['tenders'])); print('linked_expired_visible', [r.get('display_id') for r in p['tenders'] if set(r.get('linked_eshidis_ids') or []) & {'217922','216631'}])"
```

Results:

```text
py_compile: passed
focused UI tests: 86 passed
full test suite: 185 passed
local dashboard smoke without full discovery:
  total_known 95
  visible 28
  expired_hidden 3
  duplicate_hidden 8
  linked_expired_visible []
```

### UI v0.1.18 KIMDIS connected-acts forced ESHIDIS lookup

- Bumped the application version from `0.1.17` to `0.1.18`.
- Added a public read-only KIMDIS connected-acts adapter using the official
  Open Data endpoint
  `https://cerpp.eprocurement.gov.gr/khmdhs-opendata/adamChain/{referenceNumber}`.
- The adapter maps connected KIMDIS acts to public attachment endpoints,
  downloads only the returned public documents needed for evidence, extracts
  ESHIDIS ids from raw text and analyzed document text, and records per-file
  provenance/errors.
- `run_selected_fetch` for a `26PROC...` KIMDIS row now falls back to this
  connected-acts lookup when the already fetched KIMDIS document has not
  exposed a linked ESHIDIS id. If a linked id is found, the normal official
  ESHIDIS fetch path runs next; if none is found, the KIMDIS row remains a
  review candidate.
- Connected-acts findings are merged into
  `work/derived/kimdis_open_proc_documents.json`; deduplication still requires
  official ESHIDIS evidence and does not use title-only matching.
- Manual selected fetch for KIMDIS now persists `verified_tender_links` after a
  successful official ESHIDIS fetch, so user-triggered verification updates
  dashboard/dedup state immediately instead of waiting for background
  enrichment.
- Verified link persistence now deletes stale target ESHIDIS ids for the same
  source row after a successful re-verification, preventing old wrong KIMDIS
  links from remaining beside the newly proven official id.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/sources/kimdis_connected_acts.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest tests/test_db.py tests/test_kimdis_connected_acts.py tests/test_kimdis_fetch.py tests/test_ui_server.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -c "from pathlib import Path; from tender_radar.sources.kimdis_connected_acts import fetch_kimdis_connected_acts; ..."
.venv/bin/python -c "import json; from tender_radar.ui_server import run_selected_fetch; ..."
.venv/bin/python -c "import json; from tender_radar.ui_server import run_kimdis_connected_acts_lookup, kimdis_linked_eshidis_ids; ..."
.venv/bin/python -c "from tender_radar.ui_server import dashboard_payload; ..."
```

Results:

```text
py_compile: passed
focused DB/connected/KIMDIS/UI tests: 125 passed
full test suite: 192 passed
live KIMDIS Open Data smoke without full discovery:
  26PROC019367864 -> chain FETCHED, linked ESHIDIS 221566, 3 attachments, 0 errors
  26PROC019417347 -> chain FETCHED, linked ESHIDIS 221691, 3 attachments, 0 errors
selected-fetch smoke without full discovery:
  26PROC019367864 -> linked ESHIDIS 221566, official fetch ok true,
  fetch_detail_221566 returncode 0, download_files_221566 returncode 0
connected-acts merge smoke:
  26PROC019417347 -> linked ESHIDIS 221691, index ids ["221691"]
local dashboard smoke without full discovery:
  total_known 95
  visible 28
  expired_hidden 3
  duplicate_hidden 8
  visible KIMDIS rows 5
  visible KIMDIS rows with linked ESHIDIS 2
  non_verified_review 20
```

### UI v0.1.19 deadline-evidence dashboard gate

- Bumped the application version from `0.1.18` to `0.1.19`.
- The dashboard now enriches rows with fetched document evidence before
  active/expired filtering.
- Document evidence now extracts submission-deadline candidates from Greek
  declaration-like contexts, including `προθεσμία`, `καταληκτική`,
  `υποβολή προσφορών`, `παράταση` and related snippets.
- The daily front page no longer treats missing deadlines as active. A row
  must have a parseable future deadline from the source, linked official
  ESHIDIS row or document-derived evidence to appear in the actionable list.
- Unknown-deadline candidates remain review/audit data, not front-page
  bidding opportunities.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest -q
.venv/bin/python -c "from datetime import date; from tender_radar.ui_server import dashboard_payload, deadline_date; ..."
```

Results:

```text
focused UI tests: 92 passed
py_compile: passed
full test suite: 195 passed
local no-discovery dashboard smoke:
  total_known 95
  visible 13
  expired_hidden 67
  duplicate_hidden 8
  triage_hidden 1
  unknown_visible []
  expired_visible []
  document-derived deadline visible rows 4
production deploy smoke on commit 281ff78:
  package version 0.1.19
  homepage contains v0.1.19
  unauthenticated dashboard API returned 401
  production no-discovery dashboard smoke:
    total_known 113
    visible 12
    expired_hidden 74
    duplicate_hidden 9
    triage_hidden 2
    unknown_visible []
    expired_visible []
    document-derived deadline visible rows 4
```

### UI v0.1.20 hidden-deadline audit split

- Bumped the application version from `0.1.19` to `0.1.20`.
- Admin audit now enriches rows with the same fetched document evidence used by
  the dashboard.
- Hidden rows with no parseable submission deadline are reported separately as
  `NO_DEADLINE_EVIDENCE` instead of being folded into generic `EXPIRED`.
- Expired rows now include the parsed deadline in their audit reason.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_admin_audit_separates_missing_deadline_from_expired tests/test_ui_server.py -q
```

Results:

```text
focused admin/UI tests: 93 passed
py_compile: passed
full test suite: 196 passed
local admin audit smoke:
  hidden_total 125
  ai_hidden 50
  duplicates 8
  expired 3
  missing_deadline 64
production deploy smoke on commit c06f39f:
  package version 0.1.20
  homepage contains v0.1.20
  admin audit summary:
    hidden_total 144
    ai_hidden 61
    duplicates 9
    expired 13
    missing_deadline 61
    source_errors 3
  production focus rows hidden by missing deadline and not AI-hidden: 6
  production focus rows hidden by expired parsed deadline and not AI-hidden: 9
```

### UI v0.1.21 admin audit re-enrichment and mobile cards

- Bumped the application version from `0.1.20` to `0.1.21`.
- Admin audit now computes a deterministic `audit_enrichment_version`
  (`2026-07-19-deadline-v2`) without resetting runtime state and without full
  discovery.
- Missing-deadline authority rows are compared against existing official
  ESHIDIS rows using title-token overlap plus authority/location signals. A
  strong but unverified match is surfaced as `DUPLICATE_CANDIDATE`, not as a
  verified duplicate.
- The Μεσολόγγι gymnasium authority row is now explained as a possible
  duplicate of ESHIDIS `221624` with title overlap and authority match instead
  of plain `NO_DEADLINE_EVIDENCE`.
- Admin audit rows now include mobile `data-label` cells and the admin hidden
  table uses the same card-style responsive layout as the main tender list.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_admin_audit_marks_possible_eshidis_duplicate_for_missing_deadline tests/test_ui_server.py::test_admin_audit_ui_exposes_missing_deadline_and_mobile_labels tests/test_ui_server.py::test_admin_audit_separates_missing_deadline_from_expired -q
.venv/bin/python -m pytest tests/test_ui_server.py -q
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest -q
.venv/bin/python -c "from tender_radar.ui_server import admin_audit_payload; ..."
```

Results:

```text
targeted admin audit tests: 3 passed
UI tests: 95 passed
py_compile: passed
full test suite: 198 passed
local admin audit smoke:
  duplicate_candidates 1
  missing_deadline 63
  Mesologgi authority row -> DUPLICATE_CANDIDATE ESHIDIS 221624
  score 0.9
  signals title_overlap 1.00, authority_match
production deploy smoke on commit 50a0c13:
  package version 0.1.21
  homepage contains v0.1.21
  audit_enrichment_version 2026-07-19-deadline-v2
  hidden_total 144
  duplicate_candidates 1
  missing_deadline 60
  expired 13
  duplicates 9
  ai_hidden 61
  Mesologgi authority row -> DUPLICATE_CANDIDATE ESHIDIS 221624
  score 0.9
  signals title_overlap 1.00, authority_match
```

### UI v0.1.22 admin users polish

- Bumped the application version from `0.1.21` to `0.1.22`.
- The admin users API now exposes the existing SQLite row id for every admin
  user as `id`.
- The admin users table now includes an `ID` column and uses the same
  mobile-card `data-label` responsive pattern as the audit table, so email,
  role, password state and last login are readable on narrow screens.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_admin_invite_user_creates_user_role tests/test_ui_server.py::test_admin_users_payload_exposes_user_id tests/test_ui_server.py::test_admin_users_ui_has_id_and_mobile_labels -q
.venv/bin/python -m py_compile src/tender_radar/db.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest -q
```

Results:

```text
targeted admin users/version tests: 4 passed
py_compile: passed
full test suite: 200 passed
production deploy smoke on commit 99150d7:
  package version 0.1.22
  homepage contains v0.1.22
  admin users payload ok True
  users 1
  has_id True
```

### UI v0.1.23 admin role management and mobile polish

- Bumped the application version from `0.1.22` to `0.1.23`.
- Added an admin-only role update action. Admins can change a user role by
  email or visible `#ID`.
- Supported roles are now `admin`, `tester` and `user`. The UI invite form and
  role-update form use the same bounded role list.
- The role update path prevents removing the last enabled admin and prevents an
  admin from demoting their own active admin session.
- The source polling audit remains available in the DOM/API but is hidden from
  the main daily front page by default.
- Tender/admin pills now render through a wrapping `pillStack` with bounded
  width and `overflow-wrap:anywhere`, so long Greek location/status bubbles
  align cleanly on mobile.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_admin_invite_user_creates_user_role tests/test_ui_server.py::test_admin_invite_accepts_tester_role tests/test_ui_server.py::test_update_admin_user_role_accepts_email_or_id_and_protects_last_admin tests/test_ui_server.py::test_admin_users_ui_has_id_and_mobile_labels tests/test_ui_server.py::test_front_page_hides_source_audit_but_keeps_backend_audit tests/test_ui_server.py::test_dashboard_pills_use_wrapping_stack -q
.venv/bin/python -m py_compile src/tender_radar/db.py src/tender_radar/ui_server.py
.venv/bin/python -m pytest -q
```

Results:

```text
targeted admin/UI polish tests: 7 passed
py_compile: passed
full test suite: 204 passed
production deploy smoke on commit 3a61ad0:
  package version 0.1.23
  homepage contains v0.1.23
  homepage contains roleUserIdentifierInput
  homepage contains updateUserRoleBtn
  sourceAudit is hidden on the main front page
  tester role normalization passed
```

### UI v0.1.24 mobile label width and audit order check

- Bumped the application version from `0.1.23` to `0.1.24`.
- Mobile tender/admin table cards now use a wider responsive label column
  (`minmax(132px, 36%)`) so long labels such as `Προϋπολογισμός` no longer
  collide with their values.
- Confirmed on the live droplet that admin audit rows are grouped by rejection
  category, not chronological order. The current live focus dashboard reported
  11 visible rows from 14 focus candidates; the 3 hidden focus rows were
  `AI_HIDDEN`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_mobile_table_label_column_fits_long_budget_label tests/test_ui_server.py::test_dashboard_pills_use_wrapping_stack -q
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
.venv/bin/python -m pytest -q
```

Results:

```text
targeted version/mobile tests: 3 passed
py_compile: passed
full test suite: 205 passed
live pre-deploy audit check:
  visible 11
  focus candidates 14
  AI hidden 3
  duplicates 9
  duplicate_candidates 1
  expired 13
  missing_deadline 60
production deploy smoke on commit 9d10d67:
  package version 0.1.24
  homepage contains v0.1.24
  runtime STYLES_CSS contains mobile label grid minmax(132px, 36%)
```

### UI v0.1.25 chronological admin audit

- Bumped the application version from `0.1.24` to `0.1.25`.
- Admin hidden/audit rows are now sorted by the most recent audit event first,
  instead of fixed category grouping. Manual `Δεν με ενδιαφέρει` rows use
  `ignored_at`, AI hidden rows use the AI triage report `generated_at`, and
  deterministic audit rows use a persisted SQLite `admin_hidden_events`
  `first_seen_at`.
- The admin panel now shows the audit timestamp under the row source/id so the
  latest rejected/hidden item is visible directly on mobile.
- Epoch second/millisecond timestamps are normalized to ISO UTC before
  sorting/display, and placeholder `9999` values are ignored.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_admin_audit_hidden_rows_are_recent_first tests/test_ui_server.py::test_admin_audit_ui_exposes_missing_deadline_and_mobile_labels -q
.venv/bin/python -m pytest tests/test_ui_server.py::test_admin_audit_hidden_rows_are_recent_first tests/test_ui_server.py::test_admin_audit_timestamp_normalizes_epoch_ms_and_ignores_placeholders tests/test_ui_server.py::test_ui_shows_current_version_badge -q
.venv/bin/python -m pytest tests/test_ui_server.py::test_admin_audit_hidden_rows_are_recent_first tests/test_ui_server.py::test_admin_audit_timestamp_normalizes_epoch_ms_and_ignores_placeholders tests/test_ui_server.py::test_admin_audit_deterministic_rows_keep_first_hidden_time -q
.venv/bin/python -m py_compile src/tender_radar/db.py src/tender_radar/ui_server.py tests/test_ui_server.py
.venv/bin/python -m pytest -q
```

Results:

```text
targeted version/admin audit tests: 3 passed
targeted timestamp normalization tests: 3 passed
targeted SQLite first-hidden-time tests: 3 passed
py_compile: passed
full test suite: 208 passed
production deploy smoke on commit 7400b6a:
  package version 0.1.25
  homepage contains v0.1.25
  admin hidden_total 86
  hidden rows expose ISO audit_at
  repeated admin_audit_payload calls keep first_seen_at stable
```

### UI v0.1.26 disable nationwide search

- Created and pushed restore tag `restore-v0.1.25-before-disable-nationwide`
  at commit `a29a175`, the last verified production state before disabling
  nationwide search.
- Removed the user-facing All-Greece checkbox from the dashboard.
- Locked UI dashboard, AI triage, enrichment and email alert requests to
  `scope=focus`.
- Locked server dashboard scope normalization to `focus`, so manual
  `scope=all` requests no longer expose all known rows.
- Restricted CLI scheduled run and AI triage scope choices to `focus`.
- Changed search request/profile defaults from `nationwide: true` to
  `nationwide: false`.
- Recorded decision D-062: nationwide search is a future separate product gate,
  not an active workflow.

Verification:

```bash
.venv/bin/python -m pytest tests/test_ui_server.py::test_nationwide_scope_is_disabled_in_ui_and_api tests/test_ui_server.py::test_ui_shows_current_version_badge -q
# 2 passed in 0.86s

.venv/bin/python -m py_compile src/tender_radar/cli.py src/tender_radar/ui_server.py tests/test_ui_server.py
# passed

.venv/bin/python -m pytest -q
# 209 passed in 16.23s
```

Production deploy smoke on commit `f89f811` passed:

```text
package version 0.1.26
homepage has v0.1.26: True
allGreeceToggle in INDEX_HTML/APP_JS: False False
dashboard_payload(scope="all") -> scope focus
live focus visible/focus_matches: 11 / 14
```

### UI v0.1.27 Diavgeia entalmata tab

- Confirmed the existing NAS desktop utility source is available under
  `/mnt/synology/Files/Files/1. ΔΗΜΟΣΙΑ ΕΡΓΑ/1. Diavgeia_Entalmata_exe_NEW`.
  The `.env` was not opened. The Python source scans Diavgeia organizations
  `14722` and `50051`, downloads decision PDFs and keeps matches for configured
  contractor keywords.
- Ported the workflow into Tender Radar as a first-class backend module,
  `tender_radar.entalmata`, instead of embedding the Windows `.exe`.
- Added `config/diavgeia_entalmata.yml` with the Diavgeia endpoint, two
  configured regional organizations, a 15-day visible window and the current
  keyword list.
- Added SQLite table `diavgeia_entalmata`. Recent keyword matches remain
  `VISIBLE`; old visible rows move to `work/download_audit/diavgeia_entalmata/old`
  and become `ARCHIVED`; non-matches are retained as `REJECTED` evidence rather
  than deleted.
- Added CLI command `tender-radar entalmata scan`.
- Replaced the former `Αρχεία` navigation tab with `Εντάλματα`, including
  a responsive card list, summary metrics and buttons for refresh/manual scan.
- Bumped the application version from `0.1.26` to `0.1.27`.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/entalmata.py src/tender_radar/ui_server.py src/tender_radar/cli.py src/tender_radar/config.py
# passed

.venv/bin/python -m pytest tests/test_entalmata.py tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_ui_exposes_entalmata_tab tests/test_config.py -q
# 5 passed in 1.87s

.venv/bin/python -m pytest tests/test_entalmata.py tests/test_cli.py::CliTests::test_entalmata_scan_parser_has_safe_defaults tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_ui_exposes_entalmata_tab tests/test_config.py -q
# 6 passed in 0.89s

.venv/bin/python -m tender_radar config validate
# all repository configs ok, including config/diavgeia_entalmata.yml
```

Production deploy of commit `3d01a34` reached the droplet and smoke showed
package `0.1.27`, homepage `v0.1.27`, the `Εντάλματα` tab present and
`/api/entalmata` payload ok with `2` configured organizations and `6`
keywords. A first live bounded entalmata scan checked `80` Diavgeia decisions
but failed all PDF downloads because Diavgeia document URLs can contain Greek
characters that `urllib` refuses unless percent-encoded.

### UI v0.1.28 Diavgeia Greek URL encoding fix

- Added `safe_request_url()` to percent-encode non-ASCII path/query/fragment
  parts before creating `urllib.request.Request`.
- Reused the helper for both JSON and PDF fetches.
- Added regression coverage for a Diavgeia URL with Greek path/query text.
- Bumped the application version from `0.1.27` to `0.1.28`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_entalmata.py tests/test_cli.py::CliTests::test_entalmata_scan_parser_has_safe_defaults tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_ui_exposes_entalmata_tab tests/test_config.py -q
# 7 passed in 0.95s

.venv/bin/python -m py_compile src/tender_radar/entalmata.py
# passed

.venv/bin/python -m pytest -q
# 214 passed in 17.25s
```

Production deploy smoke on commit `ec5aa13` passed:

```text
package version 0.1.28
homepage has v0.1.28: True
entalmata tab present: True
bounded entalmata scan:
  checked_organizations 2
  decisions_seen 80
  outside_window 0
  without_document 0
  matched 0
  rejected 80
  errors 0
  archived 0
SQLite status counts: [('REJECTED', 80)]
```

### UI v0.1.29 Diavgeia PDF extraction parity

- Compared the NAS Windows utility implementation with the integrated
  `tender_radar.entalmata` workflow.
- Root cause: the live droplet had no `fitz`/PyMuPDF installed, and the
  first integrated extractor returned empty text instead of falling back to
  the repository document extractor. The scan downloaded the PDFs but matched
  only title/protocol fallback text, so entries whose contractor keyword was
  only inside the PDF body were rejected.
- Added fallback from `extract_pdf_text()` to the shared
  `documents.extract_text_with_metadata()` path. This uses the installed
  `pypdf` extractor and existing OCR path when needed.
- Added `PyMuPDF` to the `docs` optional dependency group so the droplet
  runtime follows the desktop utility's primary extraction method after
  deploy.
- Kept downloaded PDFs as evidence. The entalmata scan does not delete
  non-matching PDFs; it stores rejected rows in SQLite for audit/tuning.
- Bumped the application version from `0.1.28` to `0.1.29`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_entalmata.py tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_config.py -q
# 6 passed in 1.66s

.venv/bin/python -m py_compile src/tender_radar/entalmata.py
# passed

.venv/bin/python -m tender_radar config validate
# all repository configs ok

.venv/bin/python -m pytest -q
# 215 passed in 16.03s
```

### UI v0.1.30 Diavgeia paginated entalmata scan

- Confirmed that target entalmata can be outside the first Diavgeia page even
  inside the 15-day window. Live checks showed `14722` protocol `1569` on
  page `1`, and `50051` protocol `1739` on page `4`.
- Aligned `config/diavgeia_entalmata.yml` with the Windows utility endpoint
  style: `https://diavgeia.gov.gr/opendata/search` with `order=recent`.
- Added `api.max_pages` and `api.start_page` support. The production config now
  checks up to `8` pages per configured organization, stopping early when a
  page is entirely outside the visible window.
- Added test coverage that a keyword found only in a later Diavgeia page is
  downloaded, read from PDF body text and kept visible.
- Bumped the application version from `0.1.29` to `0.1.30`.

Verification:

```bash
.venv/bin/python -m pytest tests/test_entalmata.py tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_config.py -q
# 7 passed in 1.59s

.venv/bin/python -m py_compile src/tender_radar/entalmata.py src/tender_radar/config.py
# passed

.venv/bin/python -m pytest -q
# 216 passed in 20.68s
```

Production deploy smoke on commit `334b1ef` passed:

```text
package version 0.1.30
homepage has v0.1.30: True
fitz installed: True
pypdf installed: True
bounded paginated entalmata scan:
  checked_organizations 2
  pages_checked 6
  decisions_seen 240
  outside_window 126
  without_document 0
  matched 5
  rejected 109
  errors 0
  archived 0
visible entalmata:
  1793 Ρ4ΒΥΚ2Π-ΓΗΙ keywords ΛΙΑΡΟΣ, ΣΑΚΕΛΛΑΡΗΣ
  1739 6ΤΩΚΚ2Π-ΘΩΒ keywords ΛΑΤΩ
  1720 9ΨΗΛΚ2Π-ΤΨΙ keywords ΓΚΟΛΙΟΠΟΥΛΟΣ
  1569 ΨΝΚΡΚ2Π-ΠΥΥ keywords ΛΑΤΩ
  1737 Ψ7ΝΘΚ2Π-8ΩΧ keywords ΛΑΤΩ
```

### UI v0.1.31 Entalmata polish and explicit deep scan override

- The UI version was bumped from `0.1.30` to `0.1.31`.
- Navigation now presents the daily product as:
  `Δημόσια έργα`, `Αντίστροφη αναζήτηση`, `Εντάλματα`, `Admin panel`.
- The `Εντάλματα` cards expose a local retained PDF link through
  `/api/entalmata-file?ada=...` and keep the original Διαύγεια link separate.
- Entalmata records now include a best-effort deterministic `project_title`
  extracted from PDF text around common fields such as `ΤΙΤΛΟΣ ΕΡΓΟΥ`,
  `για το έργο/α:` and `με τίτλο ... συνολικού ποσού`.
- The entalmata summary now exposes `archived`, so old visible rows moved to
  `work/download_audit/diavgeia_entalmata/old` can be counted in the UI.
- Added CLI-only `tender-radar entalmata scan --max-pages N` for explicit deep
  checks such as a 100-page archive/backfill smoke without changing the normal
  UI scan depth.
- Confirmed that the future second tab should follow
  `docs/PRODUCT_SPECIFICATION.md` `MODE B — Αντίστροφη αναζήτηση
  περιεχομένου`, not a new ad hoc workflow.

Verification:

```bash
.venv/bin/python -m pytest tests/test_entalmata.py tests/test_cli.py::CliTests::test_entalmata_scan_parser_has_safe_defaults tests/test_ui_server.py::test_ui_shows_current_version_badge tests/test_ui_server.py::test_ui_exposes_entalmata_tab -q
# 9 passed in 1.31s

.venv/bin/python -m py_compile src/tender_radar/entalmata.py src/tender_radar/ui_server.py src/tender_radar/cli.py
# passed

.venv/bin/python -m tender_radar config validate
# all repository configs ok

.venv/bin/python -m pytest -q
# 217 passed in 17.53s
```

Production deploy smoke on commit `048c3a8` passed:

```text
package version 0.1.31
service active
homepage has v0.1.31: True
nav contains Αντίστροφη αναζήτηση, Εντάλματα and Admin panel
explicit deep scan:
  command: tender-radar entalmata scan --max-pages 100
  checked_organizations 2
  pages_checked 6
  decisions_seen 240
  outside_window 126
  without_document 0
  matched 5
  rejected 109
  errors 0
  archived 0
visible entalmata titles extracted:
  1793 ΑΠΟΚΑΤΑΣΤΑΣΗ ΒΛΑΒΩΝ ΤΩΝ ΥΠΟΔΟΜΩΝ ΑΡΜΟΔΙΟΤΗΤΑΣ...
  1739 ΑΠΟΚΑΤΑΣΤΑΣΗ ΒΛΑΒΩΝ ΤΩΝ ΥΠΟΔΟΜΩΝ ΑΡΜΟΔΙΟΤΗΤΑΣ...
  1720 ΣΥΜΠΛΗΡΩΜΑΤΙΚΕΣ ΠΑΡΕΜΒΑΣΕΙΣ ΚΑΙ ΕΡΓΑΣΙΕΣ...
  1569 ΣΥΝΤΗΡΗΣΗ ΟΔΙΚΟΥ ΔΙΚΤΥΟΥ Π.Ε. ΦΘΙΩΤΙΔΑΣ...
  1737 Ανάπτυξη Δικτύων Διανομής Φυσικού Αερίου...
```

### UI v0.1.32 Reverse content search scaffold

- The UI version was bumped from `0.1.31` to `0.1.32`.
- The second tab `Αντίστροφη αναζήτηση` now has a product-facing search
  surface: one query field, one search button, counters and result cards.
- Added `/api/reverse-search` as a fast read-only backend route. It searches
  only currently visible active dashboard rows from `dashboard_payload`, plus
  already available document evidence and extracted ESHIDIS document text.
- The route does not start discovery, source polling, fetch, OCR, AI triage or
  enrichment. It is deliberately scoped as the contract for future Mode B
  expansion.
- Existing technical one-off tools remain available under collapsed
  `Εργαλεία συντήρησης` to avoid breaking maintenance workflows while the
  daily second-tab experience becomes simple.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py tests/test_ui_server.py
# passed

.venv/bin/python -m pytest tests/test_ui_server.py::test_ui_exposes_reverse_search_tab tests/test_ui_server.py::test_reverse_search_payload_searches_active_dashboard_and_documents tests/test_ui_server.py::test_ui_exposes_entalmata_tab tests/test_cli.py::CliTests::test_entalmata_scan_parser_has_safe_defaults tests/test_entalmata.py
# 10 passed in 1.07s

.venv/bin/python -m pytest
# 219 passed in 16.24s
```

Production deploy smoke on commit `e24fe76` passed:

```text
package version 0.1.32
service active
reverse_search query Ναυπάκτου:
  ok true
  active_rows_searched 11
  matches 1
  first 221566
reverse_search query οδοποιία:
  ok true
  active_rows_searched 11
  matches 0
```

### UI v0.1.33 Auth cleanup and user-specific dismissals

- The UI version was bumped from `0.1.32` to `0.1.33`.
- `Δεν με ενδιαφέρει` now stores personal dismissals in SQLite
  `user_tender_dismissals` using the logged-in user email. One user's hidden
  tenders no longer disappear from another user's dashboard.
- Admin restore removes legacy and per-user dismissals for the selected row and
  keeps the existing force-keep override behavior.
- Admin audit includes user-specific dismissals with the user email in the
  reason text.
- Added password reset from the login screen. It reuses the existing
  time-limited password setup link and stores only the resulting password hash.
- Added login footer sections for `Όροι χρήσης`, `Privacy` and `Οδηγίες`.
- Replaced stale build/debug copy in discovery status with product-facing text.
- Improved missing-deadline audit reason text so new hidden rows explain the
  product reason without exposing internal `parseable` language.
- Mobile tender cards now reserve more space for row labels so long labels such
  as `Προϋπολογισμός` do not collide with values.

Verification so far:

```bash
.venv/bin/python -m py_compile src/tender_radar/db.py src/tender_radar/ui_server.py tests/test_ui_server.py
# passed

.venv/bin/python -m pytest tests/test_ui_server.py -k "version_badge or login_screen_exposes_password_reset or password_reset or dismiss or admin_audit_separates_missing_deadline or reverse_search_payload"
# 8 passed, 104 deselected

.venv/bin/python -m pytest tests/test_db.py
# 14 passed

.venv/bin/python -m pytest
# 222 passed in 17.22s
```

### Runtime v0.1.34 Scheduled entalmata and multi-recipient alerts

- The runtime/UI version was bumped from `0.1.33` to `0.1.34`; `pyproject.toml`
  was synchronized with the runtime `__version__`.
- The existing systemd command `tender-radar runtime scheduled-run` now includes
  a bounded Diavgeia entalmata scan through `config/diavgeia_entalmata.yml`.
  It writes `work/reports/diavgeia_entalmata_latest.json` and stores state in
  SQLite before the scheduled report is rendered.
- The entalmata scheduled stage is warning-only. A Διαύγεια/PDF failure is
  recorded under `warnings` and in the scheduled audit, but it does not abort
  the public-works email flow.
- Email alerts now accept multiple recipients in `ALERT_EMAIL_TO`,
  `EMAIL_ALERT_TO` or `EMAIL_TO`, separated by comma, semicolon or newline.
  Notification de-duplication remains per `row_key` and per recipient, so a
  row already sent to one mailbox can still be sent to a newly added mailbox.
- The scheduled Markdown report now includes an `Entalmata` section and exposes
  alert recipients in the `Email` section.

Verification so far:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py tests/test_ui_server.py
# passed

.venv/bin/python -m pytest tests/test_ui_server.py::test_email_alerts_payload_skips_rows_already_sent tests/test_ui_server.py::test_email_alerts_payload_supports_multiple_recipients tests/test_ui_server.py::test_scheduled_poll_and_alert_writes_audit_reports
# 3 passed in 1.20s

.venv/bin/python -m pytest
# 223 passed in 19.28s
```

Production deploy smoke on commit `6ef7089` passed:

```text
package/runtime version: 0.1.34
tender-radar-ui.service: active
tender-radar-scheduled.timer: active
local UI smoke: homepage contains v0.1.34
auth status: ok true, unauthenticated, password_users 3
scheduled dry-run: ok true, warnings []
scheduled dry-run entalmata: checked_organizations 2, pages_checked 6,
  decisions_seen 240, matched 5, rejected 109, errors 0, archived 0
email recipients parsed:
  xrgeorg@gmail.com
  xrgeorg2@gmail.com
  georgakopouloi.afoi@gmail.com
  dim.georgak@gmail.com
real email alert stage:
  candidate_rows 11
  original recipient skipped_already_sent 11
  3 newly added recipients received the current 11-row list
```

### Runtime v0.1.35 Entalmata email alerts and password-link tightening

- The runtime/UI version was bumped from `0.1.34` to `0.1.35`; `pyproject.toml`
  was synchronized with the runtime `__version__`.
- Email alerts now include a separate `Νέα εντάλματα Tender Radar` section
  when visible Diavgeia entalmata have not yet been sent to a recipient.
- Entalmata notification de-duplication is independent from public-works
  alerts. It uses SQLite `notification_log` channel `entalmata_email` and row
  keys shaped as `ENTALMA:{ADA}`, so each mailbox receives each warrant once
  and only future new warrants afterward.
- Entalmata email rows include clickable official Διαύγεια PDF/document URLs.
- Password setup/reset links now expire after `60` minutes instead of 24
  hours. They remain one-time only after successful password setup, not after a
  simple page open.
- The password setup UI and invitation email copy now state the 60-minute,
  one-use rule.

Verification so far:

```bash
.venv/bin/python -m py_compile src/tender_radar/ui_server.py
# passed

.venv/bin/python -m pytest tests/test_ui_server.py::test_password_reset_sends_setup_link_for_existing_user tests/test_ui_server.py::test_password_setup_invite_expires_after_configured_minutes tests/test_ui_server.py::test_email_alerts_payload_includes_clickable_entalmata_once_per_recipient tests/test_ui_server.py::test_email_alerts_payload_supports_multiple_recipients -q
# 4 passed in 1.84s

.venv/bin/python -m pytest
# 225 passed in 19.70s
```

Production deploy smoke on commit `53ae937` passed:

```text
package/runtime version: 0.1.35
tender-radar-ui.service: active
tender-radar-scheduled.timer: active
local UI smoke: homepage contains v0.1.35
email dry-run before entalmata send:
  candidate_rows 11
  entalmata_candidate_rows 5
  new_count 0
  new_entalmata_count 5
  skipped_already_sent 11
  entalmata_skipped_already_sent 0
real entalmata email alert stage:
  sent_emails 4
  sent notification rows 20
email dry-run after entalmata send:
  new_count 0
  new_entalmata_count 0
  skipped_already_sent 11
  entalmata_skipped_already_sent 5
```

### Local v0.1.36 Reverse pricing foundation

- The runtime/UI version was bumped from `0.1.35` to `0.1.36`.
- Added the new `pricing` user role. `admin` retains access to everything,
  `pricing` is intended for the reverse-pricing module, and plain `user`
  remains scoped to the existing ready workflows.
- Added an independent reverse-pricing SQLite foundation in
  `src/tender_radar/pricing.py`: `pricing_projects`, `pricing_documents`,
  `pricing_budget_rows`, `pricing_article_aliases` and `pricing_runs`.
- Added deterministic article/revision normalization for variants such as
  `Β-18.6`, `B18.6`, `Ο∆Ο-2312` and `ΟΔΟ-2312`.
- Added budget PDF ingestion/parsing via
  `tender-radar pricing parse-budget --pdf ... --eshidis-id ...`.
- Added read-only indexed pricing search via
  `tender-radar pricing search ...` and `/api/pricing/search`.
- The first parser gate was tested against the uploaded budget PDF fixture.
  It extracted `66` budget rows. The critical fixture row is parsed as
  `Β-18.6`, `Φράκτης απορρόφησης ενεργείας μέχρι 2000 kJ ύψους 5 m`,
  revisions `30%ΟΔΟ-2312`, `40%ΟΔΟ-2653`, `30%ΟΔΟ-2311`, unit `m`,
  quantity `100`, unit price `1680`, amount `168000`.

Verification:

```bash
.venv/bin/python -m py_compile src/tender_radar/pricing.py src/tender_radar/ui_server.py src/tender_radar/cli.py
# passed

.venv/bin/python -m pytest tests/test_pricing.py tests/test_ui_server.py -q
# 120 passed in 13.06s

.venv/bin/python -m tender_radar pricing parse-budget \
  --pdf /tmp/codex-remote-attachments/.../1-2_-προυπολογισμός-4.pdf.pdf \
  --eshidis-id 221314 \
  --db /tmp/tender_pricing_smoke.sqlite \
  --report /tmp/tender_pricing_smoke.json
# ok true, rows_extracted 66, B18.6 row parsed correctly

.venv/bin/python -m pytest -q
# 234 passed in 27.06s

.venv/bin/python -m tender_radar pricing ingest-eshidis 221566 \
  --db /tmp/tender_pricing_221566.sqlite \
  --work-dir /tmp/tender_pricing_221566_work \
  --limit 50 \
  --allow-insecure-tls \
  --report /tmp/tender_pricing_221566_skip_report.json
# ok true, downloaded 0, skipped_download 25, failed 0,
# merged rows 36, amount total 2.466.374,00

.venv/bin/python -m tender_radar pricing ingest-eshidis 221473 \
  --db /tmp/tender_pricing_221473.sqlite \
  --work-dir /tmp/tender_pricing_221473_work \
  --limit 50 \
  --allow-insecure-tls \
  --force \
  --report /tmp/tender_pricing_221473_fixed_report.json
# ok true, downloaded 10, failed 0, rows extracted 10,
# merged rows 10, missing row numbers [], merged amount total 138.253,83

.venv/bin/python -m tender_radar pricing ingest-eshidis 221473 \
  --db /tmp/tender_pricing_221473.sqlite \
  --work-dir /tmp/tender_pricing_221473_work \
  --limit 50 \
  --allow-insecure-tls \
  --report /tmp/tender_pricing_221473_skip_report_2.json
# ok true, downloaded 0, skipped_download 10, skipped_indexed 10, failed 0

.venv/bin/python -m tender_radar pricing ingest-eshidis 221689 \
  --db /tmp/tender_pricing_221689.sqlite \
  --work-dir /tmp/tender_pricing_221689_work \
  --limit 50 \
  --allow-insecure-tls \
  --force \
  --report /tmp/tender_pricing_221689_force_report.json
# ok true, attachments_found 9, downloaded 9, failed 0,
# rows upserted 41, merged rows 41, missing row numbers [],
# merged amount total 422.052,75

.venv/bin/python -m tender_radar pricing ingest-eshidis 221689 \
  --db /tmp/tender_pricing_221689.sqlite \
  --work-dir /tmp/tender_pricing_221689_work \
  --limit 50 \
  --allow-insecure-tls \
  --report /tmp/tender_pricing_221689_skip_after_parser_fix.json
# ok true, downloaded 0, skipped_download 9, skipped_indexed 9, failed 0,
# merged rows 41, missing row numbers [], merged amount total 422.052,75

.venv/bin/python -m tender_radar pricing ingest-eshidis 221691 \
  --db /tmp/tender_pricing_221691.sqlite \
  --work-dir /tmp/tender_pricing_221691_work \
  --limit 50 \
  --allow-insecure-tls \
  --force \
  --report /tmp/tender_pricing_221691_fixed_report.json
# ok true, attachments_found 8, downloaded 8, failed 0,
# rows upserted 56, merged rows 56, missing row numbers [],
# merged amount total 1.062.649,50

.venv/bin/python -c "from pathlib import Path; from tender_radar.pricing import parse_budget_rows_from_text; paths={'221473':'/tmp/tender_pricing_221473_work/extracted_text/221473/221473_1_ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf.txt','221689':'/tmp/tender_pricing_221689_work/extracted_text/221689/221689_1_ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ_signed.pdf.txt','221691':'/tmp/tender_pricing_221691_work/extracted_text/221691/221691_1_ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ_ΣΥΝΤ_ΝΑΥΠ_ΘΕΡΜΟΥ_2026_2027_signed.pdf.txt'}; [print(k, len((rows:=parse_budget_rows_from_text(Path(v).read_text(encoding='utf-8', errors='ignore'), source_document_id=1, eshidis_id=k))), min(r.row_number for r in rows), max(r.row_number for r in rows), sorted(set(range(min(r.row_number for r in rows), max(r.row_number for r in rows)+1))-set(r.row_number for r in rows)), sum(r.amount for r in rows if r.amount is not None)) for k,v in paths.items()]"
# 221473 10 1 10 [] 138253.83
# 221689 41 1 41 [] 422052.75
# 221691 56 1 56 [] 1062649.5

.venv/bin/python -m pytest -q
# 237 passed in 27.70s
```

Cron remains intentionally unchanged for the new reverse-pricing flow until
the controlled nationwide ESHIDIS fetcher, same-day cleanup and UI smoke pass.

Production deploy on commit `0c203f6` passed:

```text
GitHub Actions run: 29700913414, success
tender-radar --version on droplet: 0.1.36
tender-radar-ui.service: active
local droplet homepage contains v0.1.36
local droplet homepage contains pricingNavBtn
```

### 2026-07-20 - Reverse-pricing parser: decimal AT and bundled study layouts

The pricing parser was extended and live-smoked against the two nearest-deadline
projects from the bounded ESHIDIS pricing run:

```bash
.venv/bin/python -m tender_radar pricing ingest-eshidis 221326 \
  --db data/tender_radar.sqlite \
  --work-dir work/pricing \
  --limit 50 \
  --allow-insecure-tls \
  --force \
  --report work/reports/pricing_ingest_221326_fixed.json
# ok true, attachments_found 25, downloaded 25, failed 0,
# rows upserted 133, merged rows 133, missing row numbers [],
# merged amount total 354.581,22

.venv/bin/python -m tender_radar pricing ingest-eshidis 221271 \
  --db data/tender_radar.sqlite \
  --work-dir work/pricing \
  --limit 50 \
  --allow-insecure-tls \
  --force \
  --report work/reports/pricing_ingest_221271_fixed.json
# ok true, attachments_found 9, downloaded 9, failed 0,
# rows upserted 87, merged rows 86, missing row numbers [],
# corrected merged amount total 1.275.390,42 after amount-aware row scoring

.venv/bin/python -m pytest tests/test_pricing.py -q
# 13 passed
```

Coverage added:

- Decimal `Α.Τ.` layout whose left row numbers restart by category.
- Article suffixes split onto the next line, including Greek/alphanumeric
  suffixes such as `22.04.ΝΒΠ1`, `62.22.ΣΜ` and plain numeric suffixes such
  as `9000`.
- Bundled `ΜΕΛΕΤΗ...pdf` files that contain the actual budget table.
- Work-budget layouts with `Αρ. Τιμ.` before the revision column and integer
  quantities such as `417`, `12496`, `2000`.
- Additional units used by the new layouts, including `t`, `tkm`, `μ2`, `μ3`.

### 2026-07-20 - Reverse-pricing active ESHIDIS discovery uses full grid export

The active ESHIDIS discovery path was changed to use the public
`Εξαγωγή σε Excel` control as the primary source for the filtered active grid.
The browser DOM and captured ADF responses remain fallback diagnostics only.

Evidence:

```bash
.venv/bin/python -m tender_radar sources discover-active \
  --limit 100 \
  --allow-insecure-tls \
  --report work/reports/eshidis_active_candidates_export_smoke_100.json
# candidates_found 100
# export_rows_parsed 166
# visible_rows_seen 25
# adf_declared_row_count 166
# adf_rows_parsed 25

.venv/bin/python -m pytest tests/test_discovery.py tests/test_pricing.py -q
# 25 passed
```

This fixes the practical pagination limit for reverse-pricing active discovery:
the UI may still show/process `Νέα έργα = 15`, but candidate selection now comes
from the full exported active ESHIDIS list instead of the first rendered ADF
window.

### 2026-07-20 - UI auth session persists across reloads/restarts

Admin/pricing/user UI sessions now persist in SQLite as hashed session tokens
with a 12-hour expiry. The process-local `ADMIN_SESSIONS` map remains a cache,
but `/api/auth/status` can rebuild a session from the cookie after a service
restart or production deploy.

Logout deletes both the in-memory and SQLite session records.

### 2026-07-20 - Reverse-pricing budget audit adds document subtotal validation

Reverse-pricing budget consolidation now compares the merged database sum
against subtotal lines found in the source budget/study text, such as
`ΣΥΝΟΛΟ Α+Β`, `ΣΥΝΟΛΟ ΚΟΣΤΟΥΣ ΕΡΓΑΣΙΩΝ`, `ΔΑΠΑΝΗ ΕΡΓΑΣΙΩΝ` and
`ΣΥΝΟΛΟ ΕΡΓΑΣΙΩΝ`. The returned merge summary includes
`document_total_validation` with `OK`, `MISMATCH` or
`NO_REFERENCE_TOTAL_FOUND`, and the same audit is persisted in
`pricing_projects.metadata_json` under `pricing_budget_audit`.

The parser also now handles budget layouts like ESHIDIS `221233`, where a
bundled `ΜΕΛΕΤΗ ΕΡΓΟΥ` document contains a budget table with columns ordered as
unit, local `ΑΤ`, revision, unit price, quantity and amount. This fixes the
previous zero-row extraction for that project layout without regressing the
existing pricing fixtures.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_pricing.py -q
# 22 passed
```

### 2026-07-20 - Reverse-pricing completion now requires a full OK audit

Reverse-pricing project completion is now stricter. A pricing project is
skipped as already complete only when it has downloaded/indexed documents,
merged budget rows and a persisted `pricing_budget_audit` where both row
arithmetic and document subtotal validation are `OK`.

The subtotal validator now scans all extracted text documents for the project,
not only the documents that supplied the winning merged rows. This covers
projects where the official comparable subtotal appears in the οικονομική
προσφορά rather than inside the parsed budget table.

Live database re-audit after production deploy:

- `OK`: 3 projects (`221233`, `221689`, `221691`).
- `NEEDS_REVIEW`: 8 projects with parsed rows but arithmetic/subtotal
  mismatch or missing comparable subtotal.
- `NO_BUDGET_AUDIT`: 8 projects with no merged pricing budget yet.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_pricing.py -q
# 23 passed

gh run watch 29736834659 --repo CryptoLearningLab/dimoprasies --exit-status
# Deploy Tender Radar: success
```

### 2026-07-20 - Reverse-pricing text reprocess repairs existing budgets

Reverse-pricing now has a download-free repair path for already fetched/OCRed
pricing projects:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --report work/reports/pricing_reprocess_existing_20260720_6a88b18.json
```

The command rebuilds raw `pricing_budget_rows` from stored
`pricing_documents.text_path`, reconsolidates the merged project budget, and
updates `pricing_projects.metadata_json.pricing_budget_audit`. It skips projects
that already have a full OK audit unless `--all` is supplied.

Generic parser fixes added in this repair pass:

- category-prefixed Greek budget tables such as
  `ΟΔΟ Α-2 1 Α1 ... ΟΔΟ-1123Α m3 300 3,55 1.065,00`;
- split `m2`/`m3` where OCR places the exponent on an adjacent line;
- Greek thousand tokens without decimal comma, e.g. `1.200` as `1200`.

Live production evidence after deploy on commit `6a88b18`:

- Droplet HEAD: `6a88b18`.
- `tender-radar-ui.service`: `active`.
- Droplet tests: `tests/test_pricing.py` -> `34 passed`.
- Live reprocess summary:
  - `projects_seen`: `19`
  - `skipped_complete`: `6`
  - `completed`: `1`
  - `needs_review_or_failed`: `12`
- Newly repaired project: `221580`, now `OK` with `15` merged rows and
  `document_total_validation.status = OK`.

Current fully OK/complete reverse-pricing projects after this pass:

- `221233`
- `221369`
- `221580`
- `221615`
- `221639`
- `221689`
- `221691`

### 2026-07-20 - Reverse-pricing parser handles wrapped numeric-prefix budget rows

Added another generic reverse-pricing parser repair for budget tables where
OCR/layout extraction splits one row across two lines:

- the first line contains revision code, unit, quantity and unit price;
- the following line starts with the row number and contains description,
  article code, local `Α.Τ.` and amount.

The numeric parser now also supports English-style formatted numbers such as
`46,750.00` and `72,649.57`, which appear in some official Greek PDFs.
The same format is supported in budget subtotal/reference detection, so
document-total candidates are not truncated before validation.

This is intended to repair archived/source-extracted budget documents such as
the `221148` `ΜΕΛΕΤΗ.rar` budget, without hardcoding a project id or a specific
article.

Added a second fallback for sparse OCR summary-budget tables where some rows
lost the unit/unit-price columns but still retain row number, article/revision
evidence, quantity and amount. The parser derives the missing unit price from
`amount / quantity`, marks the unit as `UNKNOWN`, and only accepts rows whose
arithmetic reconciles. This targets source layouts like `221695` while
remaining a fallback after the normal structured parsers fail.

The subtotal validator also recognizes OCR-corrupted `ΣΥΝΟΛΟ` labels such as
`ΣWΝ ΟΛΟ` and excludes `ΑΠΟΛΟΓΙΣΤΙΚΑ` totals from the comparable works-subtotal
reference set.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_pricing.py
# 39 passed

.venv/bin/python -m py_compile src/tender_radar/pricing.py
# passed
```

Live production evidence after deploy on commit `e3c2992`:

- Droplet HEAD: `e3c2992`.
- Droplet focused tests: `tests/test_pricing.py` -> `39 passed`.
- `221148` repaired to `OK` after archive extraction and wrapped-row parsing:
  `4` merged rows, total `49.816,00`, document-total validation `OK`.
- `221695` repaired to `OK` after sparse OCR parsing:
  `5` merged rows, total `49.460,00`, document-total validation `OK`.
- Current reverse-pricing SQLite audit:
  - `OK`: `9`
  - `NEEDS_REVIEW`: `10`
  - `NO_BUDGET_AUDIT`: `0`

### 2026-07-20 - Reverse-pricing parser recognizes collapsed OCR budget streams

Added a guarded fallback parser for OCR outputs where a budget table is
collapsed into a long text stream instead of line-oriented rows. The parser
splits row markers such as `1]`, `2|`, `3 [` and only accepts candidate rows
when:

- a known unit is followed by a plausible numeric tail;
- row arithmetic reconciles;
- article/revision evidence can be found in the segment.

The rule also normalizes OCR variants such as `YAP`/`ΥΑΡ` for `ΥΔΡ` revision
codes and `ΙΝΑΟΔΟ` for `ΝΑΟΔΟ` article prefixes. This is deliberately a
fallback after the structured parsers fail or produce too few rows.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_pricing.py
# 40 passed

.venv/bin/python -m py_compile src/tender_radar/pricing.py
# passed
```

Live production evidence after deploy on commit `bd62d0a`:

- Droplet HEAD: `bd62d0a`.
- Droplet focused tests: `tests/test_pricing.py` -> `40 passed`.
- `220423` improved from zero-row to partial parsed state:
  `19` raw rows, `15` merged rows, amount total `129.128,20`.
- `220423` remains `NEEDS_REVIEW` because document-total validation correctly
  rejects the partial parse against official reference total `1.510.058,05`.
- `221452` remains `NEEDS_REVIEW` with zero parsed rows; the available OCR text
  has row markers but loses enough numeric/unit data that the arithmetic guard
  rejects it.
- Current reverse-pricing SQLite audit:
  - `OK`: `9`
  - `NEEDS_REVIEW`: `10`

### 2026-07-20 - Reverse-pricing AI fallback guarded by local row arithmetic

Added an optional OpenAI fallback for damaged OCR budget tables. The fallback is
available through:

```bash
tender-radar pricing reprocess-existing --use-ai-fallback --ai-fallback-mode empty
```

or, for controlled comparison runs:

```bash
tender-radar pricing reprocess-existing --use-ai-fallback --ai-fallback-mode always
```

The fallback does not promote projects to complete by itself. OpenAI returns
candidate budget rows as strict JSON, then the local parser normalizes them into
`PricingBudgetRow` objects and rejects any row where `quantity * unit_price`
does not reconcile to `amount`. AI-extracted rows are also rejected unless
their sum matches an official subtotal found in the same extracted text. This
deliberately rejects AI rows from OCR text that has no parseable subtotal, even
if each individual row is arithmetically valid. Project completion still
requires the existing merged-budget audit and official document-total validation
to pass.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_pricing.py
# 41 passed

.venv/bin/python -m py_compile src/tender_radar/pricing.py src/tender_radar/cli.py tests/test_pricing.py
# passed

.venv/bin/python -m pytest
# 271 passed
```

Live production evidence after deploy on commit `350458d`:

- Droplet HEAD: `350458d`.
- Runtime version: `tender-radar 0.1.40`.
- Droplet focused tests: `tests/test_pricing.py` -> `42 passed`.
- Targeted AI fallback run for `221452` and `221006` stayed `NEEDS_REVIEW`.
  Both projects have official offer subtotals in extracted text, but the
  fallback produced no rows that passed same-document subtotal validation.
- Live SQLite check after the reprocess confirmed zero persisted
  `pricing_budget_rows` for `221452` and `221006`, so rejected AI extraction did
  not pollute the pricing database.

### 2026-07-20 - AI budget router connected to guarded reprocess

Reverse-pricing now has an optional AI budget router connected to
`pricing reprocess-existing`:

```bash
tender-radar pricing reprocess-existing --use-ai-budget-router
```

The router runs before deterministic parsing and selects the most likely
budget document/page range. It stores compact routing evidence in
`pricing_projects.metadata_json.pricing_budget_route` and the command report.
It does not write budget rows directly.

If the routed parse fails local row arithmetic or official document-total
validation, the command automatically falls back to full deterministic
reprocess for the project. This keeps the router useful as a prioritization
layer while preventing it from degrading the persisted project budget.

Evidence:

```bash
.venv/bin/python -m py_compile src/tender_radar/pricing.py src/tender_radar/cli.py
# passed

.venv/bin/python -m pytest tests/test_pricing.py
# 46 passed
```

Production deploys on commits `e290b45` and `b72ff0c` passed through GitHub
Actions. Live smoke on the droplet:

```bash
tender-radar pricing reprocess-existing --db data/tender_radar.sqlite \
  --eshidis-id 220675 --use-ai-budget-router \
  --report work/reports/pricing_reprocess_220675_ai_router_guarded.json
```

Result: the AI router selected document id `232`, but the routed parse did not
pass validation, so the new fallback reprocessed all `69` extracted documents.
The project remains `NEEDS_REVIEW` with `17` merged rows and no trusted
reference monetary total. This is expected: the router integration is now safe,
but `220675` still needs classification/parser work before it can become `OK`.

### Local v0.1.41 reverse-pricing budget route guard

- The runtime/UI version was bumped from `0.1.40` to `0.1.41`.
- Reverse-pricing now treats standalone official ESHIDIS budget/pro-measurement
  attachments as first-class router candidates. Files named with
  `ΠΡΟΜΕΤΡΗΣΗ`/`ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` receive explicit priority over nested ZIP/study
  summaries, and the AI budget-router prompt now carries local/text
  availability plus extraction-quality hints.
- Pricing ingestion with `keep_heavy_files=False` now preserves official
  standalone budget/pro-measurement PDFs instead of deleting them immediately.
  Other downloaded heavy files may still be cleaned up.
- When cleanup deletes a non-preserved heavy file, SQLite clears
  `pricing_documents.local_path` and records `heavy_file_deleted_at`, avoiding
  stale paths that point to files no longer on disk.
- ZIP extraction now repairs common legacy Greek filename encodings before
  indexing extracted child PDFs.

Evidence:

```bash
.venv/bin/python -m py_compile src/tender_radar/pricing.py tests/test_pricing.py
# passed

.venv/bin/python -m pytest tests/test_pricing.py
# 49 passed
```

### Local v0.1.48 reverse-pricing 219930 lump-sum budget fix

- The runtime/UI version was bumped from `0.1.47` to `0.1.48`.
- A live SQLite health check showed `22` reverse-pricing projects in
  `data/tender_radar.sqlite`, with `497` pricing files on disk and `168`
  extracted-text artifacts.
- The health check also confirmed that several older projects have parsed
  rows/text artifacts but stale or cleaned-up PDF paths. This is a database
  hygiene issue for later cleanup/refetch, not evidence that every historical
  project still has a true local PDF download.
- A live backup was created before touching pricing state:
  `data/backups/tender_radar_before_219930_health_20260720T215403Z.sqlite`.
- Targeted ingest for ESHIDIS `219930` downloaded all `15/15` official
  attachments and extracted text from the standalone
  `ΝΕΟΣ ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ ΜΕΛΕΤΗΣ.pdf`.
- The failed layout was identified as a lump-sum / `κατ' αποκοπή` budget:
  the trusted official works subtotal is `2.988.598,87`, while the previous
  parser selected a nested fan-coil schedule row from a ZIP and produced one
  invalid row totaling `50,00`.
- The parser now handles lump-sum budget texts by creating one validated
  budget row from the official `Συνολική Δαπάνη Εργασιών` total, and archive
  child documents no longer become pricing candidates merely because the leaf
  filename contains the broad word `ΜΕΛΕΤΗ`.

Evidence:

```bash
.venv/bin/python -m py_compile src/tender_radar/pricing.py
# passed

.venv/bin/python -m pytest tests/test_pricing.py::test_parse_budget_rows_handles_lump_sum_budget_total \
  tests/test_pricing.py::test_pricing_candidate_document_skips_drawings_inside_meleti_archive
# 2 passed

.venv/bin/python -m pytest tests/test_pricing.py
# 55 passed
```

## Handoff Discipline

Every future substantial Codex task should:

1. Read `docs/HANDOFF.md` after `docs/INDEX.md`.
2. Update `docs/PROGRESS.md` with commands, evidence, failures and tests.
3. Update `docs/DECISIONS.md` only for real architectural/product decisions.
4. Update `tasks/NEXT_TASK.md` with one executable next gate.
5. Update `docs/HANDOFF.md` when the overall project state, repo access,
   deployment path, or next gate changes.
6. Commit and push tracked documentation/code changes to GitHub unless the
   user explicitly requests local-only work.
