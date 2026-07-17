# Project Progress

## Current Phase
`PHASE_2_SQLITE_VERTICAL_SLICE_PARTIAL`

## Last Updated
`2026-07-17`

## Current Task
`tasks/NEXT_TASK.md`

## Completed Milestones
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
content_matches: 60
status_reports: 1
ui_dashboard_scope_focus_rows: 14
ui_dashboard_scope_all_rows: 32
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
```

## Next Gate

Expanded report follow-up: fetch official KIMDIS attachments for the 11 open
PROC candidates, then verify exact place/authority evidence and deduplicate
related/cancelled notice pairs.

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
