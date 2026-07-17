# Project Handoff

Last updated: `2026-07-17`

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

## Current Verification

Latest confirmed command:

```bash
.venv/bin/python -m pytest
```

Result:

```text
39 passed in 1.18s
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
- Authentication-safe adapter for TEE subscription sources.
- Production access model for UI beyond local/LAN/Tailscale/private tunnel.

## Next Work

Follow `tasks/NEXT_TASK.md`.

Current intended next gate:

Run the controlled attachment download and document analysis gate for candidate
`221629`, then evaluate it with `config/evaluation_profiles/public_works_dynamic.yml`.
