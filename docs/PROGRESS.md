# Project Progress

## Current Phase
`PHASE_2_SQLITE_VERTICAL_SLICE_PARTIAL`

## Last Updated
`2026-07-19`

## Current Task
`tasks/NEXT_TASK.md`

## Completed Milestones
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
