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

## Tests Last Run
- `.venv/bin/python -m pytest tests/test_status.py tests/test_cli.py`
- Result: 12 passed.
- `.venv/bin/python -m pytest`
- Result: 39 passed.

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
discovered_active_candidates: 15
verified_active_matches: 0
unknown_statuses: 6
unexplained_failures: 0
```

## Next Gate

Download/analyze follow-up: run the controlled attachment download and document
analysis gate for candidate `221629`, then evaluate it with
`config/evaluation_profiles/public_works_dynamic.yml` and keep status
verification separate from content matches.

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
