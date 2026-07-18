# Project Handoff

Last updated: `2026-07-18`

This is the compact handoff for a new Codex chat starting from zero.

## Repository

- Main workspace: `/root/dimoprasies`
- GitHub repo: `https://github.com/CryptoLearningLab/dimoprasies`
- Main branch: `main`
- Initial baseline commit: `9f556be Initial public works tender radar snapshot`
- Access: the repo may be public or private. Codex access is through the
  GitHub deploy key named `dimoprasies-codex`; keep `Allow write access`
  enabled if Codex must push updates.

## Read Order

For a fresh chat, read these before changing code:

1. `AGENTS.md`
2. `PLANS.md`
3. `docs/INDEX.md`
4. `docs/HANDOFF.md`
5. `docs/PRODUCT_SPECIFICATION.md`
6. `docs/IMPLEMENTATION_PHASES.md`
7. `docs/PROGRESS.md`
8. `docs/DECISIONS.md`
9. `docs/KNOWN_LIMITATIONS.md`
10. `tasks/NEXT_TASK.md`

Then inspect the implementation files relevant to the current task.

## Mission

Build a daily-use tool for discovering, archiving, searching and evaluating
Greek public works tenders. The first production direction is public ESHIDIS
data, official tender attachments, SQLite persistence, full-document search
and editable YAML/UI evaluation rules.

## What Exists

- Python package and CLI under `src/tender_radar`.
- Console script `tender-radar`.
- UI console script `tender-radar-ui`.
- SQLite schema in `src/tender_radar/schema.sql`.
- Local SQLite sample database at `data/tender_radar.sqlite` kept out of git.
- Public ESHIDIS source audit tools under `tools/`.
- Direct public ESHIDIS detail endpoint support:
  `resources/search/{eshidis_id}`.
- Live sample tender:
  - ESHIDIS id: `221744`
  - Title: `ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027`
  - Official attachment rows: `8`
  - Downloaded attachments in local `work/download_audit/`
  - Analyzed documents and extracted text in local `work/extracted_text/`
- Additional official candidate detail imports with attachment rows:
  - `221380`: 24 latest attachment rows
  - `221629`: 10 latest attachment rows
  - `221675`: 9 latest attachment rows, all downloaded and analyzed
- Discovery command for public active-candidate grid:
  `sources discover-active`.
- Detail import command:
  `sources fetch-resource`.
- Attachment download command:
  `sources download-attachment`.
- Document analysis command:
  `documents analyze`.
- Profile search command:
  `search run`.
- Dynamic evaluation command:
  `evaluate run`.
- Search profiles:
  - `config/search_profiles/road_maintenance.yml`
  - `config/search_profiles/rockfall_energy_barrier.yml`
- Dynamic evaluation profile:
  - `config/evaluation_profiles/public_works_dynamic.yml`
- Editable Rules UI in `src/tender_radar/ui_server.py`.
- UI tabs:
  - Discovery
  - Tender
  - Rules
  - Reports
- Windows launchers for local, LAN and Tailscale use.
- Docker/Synology docs:
  - `Dockerfile`
  - `compose.yaml`
  - `docs/SYNOLOGY_DEPLOY.md`

## Recent Remote Work

- The project was moved into `/root/dimoprasies`.
- The GitHub repo `CryptoLearningLab/dimoprasies` was initialized from this
  local project.
- A dedicated SSH deploy key `dimoprasies-codex` was created for this repo.
- `main` was pushed to GitHub successfully.
- The local UI was run with:

```bash
.venv/bin/tender-radar-ui --host 0.0.0.0 --port 8765
```

- A temporary public tunnel was tested through `localhost.run`:

```text
https://b608b69a6b7e08.lhr.life
```

That URL is temporary and should not be treated as stable infrastructure.
- The delayed ESHIDIS attachment table issue for `221380`, `221629` and
  `221675` was traced to snapshotting before the Oracle ADF streamed table
  loaded. `fetch_resource_audit` now waits for `#t1::db` and download controls.
- The UI report endpoint for candidate JSON now sends
  `application/json; charset=utf-8`, fixing Greek text rendered as symbols in
  browser tabs.
- Candidate `221675` completed controlled download and analysis:
  - 9 official attachments downloaded
  - 9 documents analyzed with extracted text
  - dynamic evaluation matched 1 tender with score `14.0` and 6 hits
  - advisory status verification checked 9 latest attachments and 9 analyzed
    documents
  - recommended status is `POSSIBLY_ACTIVE` with confidence `0.65`
  - `verified_active` remains `false`; SQLite status remains `UNKNOWN`
- The local UI first screen was redesigned for non-technical daily use:
  - default local-interest scope from `config/locations.yml`
  - all-Greece presentation toggle
  - essential tender table
  - official ESHIDIS link
  - `Download files`
  - preview of declaration, technical description and budget where available
- `docs/AVAILABLE_MECHANISMS.md` records the mechanisms available behind the
  UI so future UI work composes them instead of replacing them.
- Uploaded source whitelist is integrated as:
  - `docs/SOURCE_WHITELIST.md`
  - `config/sources.yml`
- Deduplication protocol is integrated as:
  - `docs/DEDUPLICATION.md`
  - `config/deduplication.yml`
- Title-only deduplication is forbidden. Ambiguous repeated-title cases stay
  separate or become `POSSIBLY_RELATED` until official identifiers or strong
  composite evidence prove identity.
- `sources audit-whitelist` checks configured source reachability, known
  adapters and fallback availability without starting a full crawl. Latest
  audit checked 31 entries: 24 reachable, 3 failed, 0 adapter-required,
  4 URL templates requiring known identifiers, 2 failed-with-fallback and
  0 unresolved blockers. The failed entries are ESHIDIS active search
  short-timeout retry and two Patras municipal pages that timed out; Patras has
  reachable Diavgeia/DEYAP fallbacks. KIMDIS PROC/AWRD/SYMV POST probes now
  return HTTP 200 with documented `contractType: "10"` request bodies.
- `sources expanded-report` builds a controlled discovery report from ESHIDIS
  candidates and KIMDIS Open Data. Latest run checked 5 KIMDIS pages per
  PROC/AWRD/SYMV family: 750 total KIMDIS records, 53 focus-related records,
  0 runtime errors. The report was emailed to the authenticated Gmail account
  as `work/reports/expanded_discovery_report.md`.
- Expanded-report records are now classified by submission stage using KIMDIS
  `finalSubmissionDate` as of `2026-07-17`: 11 focus PROC records are
  `SUBMISSION_OPEN_CANDIDATE`, 1 focus PROC is `CANCELLED_NOTICE`, and 41 focus
  AWRD/SYMV records are historical award/contract records.
- Δήμος Αμφιλοχίας has been added as a focus geography with 5 public sources:
  official prokiryxis, official invitations of interest, mayor decisions,
  municipal council decisions and Diavgeia. Latest source whitelist audit after
  this addition checked 36 sources: 29 reachable/ready, 3 failed,
  0 adapter-required and 0 unresolved blockers.
- Amfilochia aliases include `Θεριακήσι`, `Θεριακήσιο` and `Θεργιακήσι`.
  Focus matching normalizes Greek text with Unicode casefold and
  accent/diacritic removal so uppercase/lowercase and accented/unaccented
  variants do not need to be duplicated in configuration.
- UI focus matching now treats configured `included_regional_units` as the
  regional constraint when present. Broad NUTS prefix matching is only used
  for regions without explicit included units, preventing `EL644 - Φθιώτιδα`
  from being shown as `Περιφέρεια Στερεάς Ελλάδας - Φωκίδα`.
- The UI first-screen dashboard now includes KIMDIS expanded-report
  `focus_open_proc_candidates` alongside ESHIDIS/discovery/SQLite rows. KIMDIS
  rows are shown as `SUBMISSION_OPEN_CANDIDATE` with source label `ΚΗΜΔΗΣ`,
  ADAM official ids and attachment links; ESHIDIS preview/download actions stay
  disabled for KIMDIS rows.
- The `Νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ` button now runs a real refresh sequence:
  ESHIDIS `sources discover-active`, then KIMDIS/ESHIDIS
  `sources expanded-report`, then dashboard reload.
- Latest live UI search found 15 ESHIDIS discovery candidates and refreshed the
  expanded report to 765 total candidates, 51 focus candidates and 12 KIMDIS
  `SUBMISSION_OPEN_CANDIDATE` PROC notices. The dashboard currently shows 14
  focus rows: 12 KIMDIS rows plus 2 ESHIDIS rows.
- `Γλυφάδα` was tightened to `Γλυφάδα Δωρίδος` to avoid false positives from
  Δήμος Γλυφάδας Αττικής.
- `sources fetch-kimdis-open-proc` now fetches official KIMDIS attachment URLs
  for open PROC candidates from the expanded report, stores local files under
  `work/download_audit/kimdis/`, records size/SHA-256/provenance, extracts
  supported PDF/XML text for the shortlist report and checks document text for
  authority/scope evidence from `config/sources.yml`.
- Latest KIMDIS fetch gate checked 12 open PROC candidates, kept all statuses
  candidate-only, had 12 official PDFs present, extracted text from 12 PDFs,
  found document authority/scope evidence in 12 records and had 0 failed
  fetches. The generated runtime reports are
  `work/reports/kimdis_open_proc_fetch_report.json` and
  `work/reports/kimdis_open_proc_fetch_report.md`.
- KIMDIS PROC attachment metadata and extracted text are now persisted as
  runtime artifacts:
  - `work/derived/kimdis_open_proc_documents.json`
  - `work/extracted_text/kimdis/*.txt`
- The UI dashboard joins KIMDIS open PROC rows with that document index. Rows
  with local files expose Preview and Download file actions through
  `/api/kimdis-document-preview?official_id=...` and
  `/api/kimdis-document-file?official_id=...`.
- The UI table uses separate `Α/Α` and `Πηγή` columns. The `Εργαλεία` page has
  both an ESHIDIS id input and a KIMDIS ADAM input. Document previews render
  all available documents rather than only the featured subset.
- The first dashboard is now the primary document workflow. Each tender row
  exposes `Fetch`, which detects the first-column identifier as either ESHIDIS
  numeric id or KIMDIS `26PROC...` ADAM and fetches only that row's official
  documents, plus `ZIP`, which streams all already downloaded local documents
  for that row as one archive.
- `sources fetch-kimdis-open-proc` supports `--official-id` for single-ADAM
  fetches. The older batch fetch remains available for full open-PROC refreshes.
- The UI shows a modal progress overlay while long-running fetch/download
  actions are active. Commands remain serialized because they write shared
  runtime reports and document indexes.
- Discovery defaults are safer for non-daily use: ESHIDIS active discovery
  now defaults to `100` rows and KIMDIS expanded report to `20` pages per
  record family. The UI displays that depth. This reduces miss risk but is
  still bounded scanning, not a formal no-miss guarantee. The next reliability
  gate should add persisted discovery watermarks/backfill so a run after a
  week scans until it covers the previous successful window or source
  exhaustion.
- Long-running UI actions use in-memory background jobs. Heavy POST endpoints
  return `202` with a `job_id`; the browser polls `/api/jobs/{job_id}` every
  5 seconds. This avoids browser/tunnel/server request timeouts while keeping
  CLI commands serialized through `COMMAND_LOCK`.
- Dashboard rows are clickable and update the preview pane. The selected row
  is highlighted, while action buttons/links stop event propagation. The user
  confirmed one successful end-to-end tunnel workflow: per-row `Fetch` plus
  `ZIP` download.
- Ambiguous place aliases are recall-first. `Γλυφάδα` and `Γλυφάδας` are
  configured as ambiguous aliases for Δήμος Δωρίδος: positive context such as
  `Δωρίδος`, `Φωκίδα` or `EL645` confirms the match; negative context such as
  `Δήμος Γλυφάδας`, `Αττική` or `EL30` blocks it; otherwise the candidate is
  retained for review with a match note. The current live expanded report has
  0 ambiguous retained matches.
- KIMDIS fetched documents now extract explicit linked ESHIDIS numeric ids
  from context such as `Α/Α ΕΣΗΔΗΣ`. A KIMDIS dashboard row `Fetch` first
  fetches the selected ADAM, then automatically runs ESHIDIS `fetch-resource`
  and `download-attachment --all` for any linked ESHIDIS id found. This is a
  provenance cross-reference only, not title-based merge or active-status
  promotion.
- The linked ESHIDIS extractor also handles dotted official acronym text such
  as `Ε.Σ.Η.ΔΗ.Σ Α/Α :207024` near Promitheus/eProcurement links. The verified
  KIMDIS example `26PROC019429074` now links to ESHIDIS `207024`, which has
  14 latest local ESHIDIS files available for ZIP.
- The extractor also reads official resource URLs in declaration article 2.2,
  such as
  `pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/<id>`, and
  the fully dotted acronym `Ε.Σ.Η.Δ.Η.Σ.`. A corpus check found 10 extracted
  text files with official resource URLs and extracted all 10/10. The latest
  KIMDIS document index has 9 records with linked ESHIDIS ids.
- Single-ADAM KIMDIS fetches merge their updated document record into the
  existing KIMDIS document index instead of replacing the full index. KIMDIS
  previews expose a linked ESHIDIS file count so the UI distinguishes
  "linked id found" from "downloaded ESHIDIS files already available".
- KIMDIS row ZIP archives include the local KIMDIS document and any already
  downloaded latest ESHIDIS files for linked ESHIDIS ids.
- Discovery watermark/backfill safety is implemented for the UI discovery
  action. Each run writes runtime metadata to
  `work/derived/discovery_runs.json`: mode, started/completed timestamps,
  source family, ESHIDIS row limit, KIMDIS page depth, candidate ids, partial
  failures, source exhaustion flags and previous-window overlap.
- The UI now labels the quick scan as bounded and exposes a `Backfill safety`
  checkbox. Backfill mode repeats discovery at increasing depth until it
  reaches ids from the previous successful run window or hits the configured
  maximum depth.

## Current Verification

Latest confirmed command:

```bash
.venv/bin/python -m pytest
```

Result:

```text
87 passed in 2.04s
```

Latest KIMDIS PROC attachment fetch command:

```bash
.venv/bin/python -m tender_radar sources fetch-kimdis-open-proc --expanded-report work/reports/expanded_discovery_report.json --config config/sources.yml --download-dir work/download_audit/kimdis --text-dir work/extracted_text/kimdis --document-index work/derived/kimdis_open_proc_documents.json --report work/reports/kimdis_open_proc_fetch_report.json --markdown-report work/reports/kimdis_open_proc_fetch_report.md --limit 12 --timeout 30 --allow-insecure-tls --retries 2 --retry-delay 30 --request-delay 5
```

Result:

```text
12 checked, 12 already present, 0 failed, 12 text extracted,
12 document evidence found, 12 text artifacts
```

Latest whitelist audit command:

```bash
.venv/bin/python -m tender_radar sources audit-whitelist --allow-insecure-tls --timeout 8 --report work/reports/source_whitelist_audit.json --markdown-report work/reports/source_whitelist_audit.md
```

Result:

```text
36 checked, 29 reachable/ready, 3 failed, 0 adapter-required, 4 templates,
2 failed-with-fallback, 0 unresolved blockers
```

Latest status verification command:

```bash
.venv/bin/python -m tender_radar status verify --eshidis-id 221675 --report work/reports/status_verification_221675.json --markdown-report work/reports/status_verification_221675.md
```

Result: `POSSIBLY_ACTIVE`, confidence `0.65`, `verified_active = false`.

The system `python` command is not present in the remote environment; use
`.venv/bin/python` or `python3`.

## Non-Negotiable Rules

- Do not use `VERIFIED_ACTIVE` without official detail/status evidence.
- Keep content match separate from active-status verification.
- Keep rules, phrases, scores and filters in YAML/UI, not hardcoded in core.
- Do not commit TEE subscription credentials or any other secrets.
- Treat TEE as a future authenticated adapter with local runtime secrets only.
- Do not commit `.venv`, caches, downloaded originals, SQLite runtime data or
  report artifacts unless explicitly converted into curated fixtures/docs.
- Do not delete original evidence or downloaded source material.
- After meaningful work, update:
  - `docs/PROGRESS.md`
  - `docs/DECISIONS.md` when there is a real decision
  - `tasks/NEXT_TASK.md`

## What Is Missing

- Production-grade source adapter coverage beyond the proven sample flow.
- Persisted status history/transitions; current `status verify` reports are
  advisory and do not update `tenders.status`.
- Strong active-status verification model. Discovery rows remain
  `DISCOVERED_ACTIVE_CANDIDATE` until verified by official evidence.
- OCR for scanned PDFs.
- Robust CA/trust-store fix so production HTTPS fetches do not need
  `--allow-insecure-tls`.
- Database migration runner.
- Export generator for daily reports.
- Scheduling/background daily run.
- Deduplicated change detection across repeated scans.
- Persisted discovery watermarks/backfill exists for UI-triggered discovery.
  Scheduling and notification of newly seen candidates is still missing.
- Authentication-safe adapter for TEE subscription sources.
- Production access model for UI beyond local/LAN/Tailscale/private tunnel.
- Manual browser review of the redesigned first UI screen.
- Full persistence/export path for KIMDIS Open Data results; current whitelist
  audit proves POST readiness but does not yet import every KIMDIS result into
  SQLite.
- Runtime retry monitoring for Patras pages that timed out in the whitelist
  audit; reachable fallbacks exist for the same scope.
- Verification/prioritization of expanded KIMDIS discovery records. The latest
  53 focus-related records are candidates, not `VERIFIED_ACTIVE` tenders.
- Search/evaluation over KIMDIS text artifacts. The current search/evaluation
  pipeline still primarily uses SQLite ESHIDIS documents.
- Municipal-source document fetching is still future work. Once municipal
  adapters download documents, they should reuse the same explicit
  KIMDIS/municipal-document to ESHIDIS-id cross-reference path.

## Next Work

Follow `tasks/NEXT_TASK.md`.

Current intended next gate:

Add scheduled discovery/report notification wiring so a cron/container job can
run discovery, compare against the previous successful watermark and notify
only for newly seen active candidates.
