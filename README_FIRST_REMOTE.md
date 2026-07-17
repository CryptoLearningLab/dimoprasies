# Read Me First - Remote Continuation

This file is the handoff note for continuing the Public Works Tender Radar
project inside the remote environment at:

```text
/root/dimoprasies
```

Use it before making changes.

## 1. Read These First

Read these files in order:

1. `AGENTS.md`
2. `README.md`
3. `docs/PRODUCT_SPECIFICATION.md`
4. `docs/IMPLEMENTATION_PHASES.md`
5. `docs/HANDOFF.md`
6. `docs/PROGRESS.md`
7. `docs/DECISIONS.md`
8. `docs/KNOWN_LIMITATIONS.md`
9. `tasks/NEXT_TASK.md`

Then inspect:

- `pyproject.toml`
- `src/tender_radar/cli.py`
- `src/tender_radar/ui_server.py`
- `src/tender_radar/evaluation.py`
- `config/evaluation_profiles/public_works_dynamic.yml`
- `config/search_profiles/road_maintenance.yml`
- `config/search_profiles/rockfall_energy_barrier.yml`

## 2. Remote Setup

The project has already been copied to `/root/dimoprasies`.

Known remote state:

- Python 3.12.3 exists.
- `.venv` exists.
- `.venv/bin/python -m tender_radar --help` works.
- `.venv/bin/python -m pytest` passed with `32 passed`.
- GitHub repo `CryptoLearningLab/dimoprasies` has branch `main`.
- Latest confirmed pushed commit is
  `e5bcef5 Document project handoff and remote status`.
- Codex push access uses the dedicated deploy key `dimoprasies-codex`.

Set up the environment:

```bash
cd /root/dimoprasies
python3 --version
python3 -m venv .venv
```

If `venv` fails with `ensurepip is not available`, install:

```bash
apt update
apt install -y python3.12-venv
```

Then:

```bash
cd /root/dimoprasies
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Optional extras for browser/document work:

```bash
python -m pip install -e ".[browser,docs,dev]"
python -m playwright install chromium
```

## 3. Verify Functionality

Run:

```bash
cd /root/dimoprasies
. .venv/bin/activate

python -m tender_radar --help
python -m tender_radar config validate
python -m pytest
```

Expected current remote result:

```text
32 passed
```

Then verify the existing sample evaluation:

```bash
python -m tender_radar evaluate run \
  --profile config/evaluation_profiles/public_works_dynamic.yml \
  --eshidis-id 221744 \
  --report work/reports/evaluation_public_works_dynamic_221744_remote.json \
  --markdown-report work/reports/evaluation_public_works_dynamic_221744_remote.md
```

## 4. What Already Exists

This project is a daily-use tool for discovering and evaluating Greek public
works tenders.

Already implemented:

- Python package/CLI `tender-radar`.
- Config validation.
- SQLite schema and database at `data/tender_radar.sqlite`.
- Public ESHIDIS source audit.
- Direct public ESHIDIS endpoint: `resources/search/{eshidis_id}`.
- Live sample tender `221744`.
- 8 downloaded/analyzed attachments for `221744`.
- Downloaded files under `work/download_audit`.
- Extracted text under `work/extracted_text`.
- Document classification and PDF text extraction.
- Search profiles:
  - `road_maintenance.yml`
  - `rockfall_energy_barrier.yml`
- Commands:
  - `sources health`
  - `sources discover-active`
  - `sources fetch-resource`
  - `sources download-attachment`
  - `documents analyze`
  - `search run`
  - `evaluate run`
- Dynamic evaluation profile:
  - `config/evaluation_profiles/public_works_dynamic.yml`
- Existing evaluation rule:
  - foundation excavation unit price greater than 5 EUR.
- Local UI server:
  - `src/tender_radar/ui_server.py`
- UI tabs:
  - Discovery
  - Tender
  - Rules
  - Reports
- Editable evaluation rules through the UI.
- Docker/Synology/Tailscale files:
  - `Dockerfile`
  - `compose.yaml`
  - `docs/SYNOLOGY_DEPLOY.md`

## 5. Project Rules

Do not break these:

1. Do not mark anything `VERIFIED_ACTIVE` without official detail/status evidence.
2. Keep content matches separate from active/status verification.
3. Keep technical phrases, scores and numeric filters in YAML/UI, not hardcoded.
4. Never store TEE subscription credentials in the repository.
5. Treat TEE as a future authenticated adapter using runtime secrets only.
6. Do not make destructive changes.
7. Do not delete downloaded originals or source evidence.
8. Do not touch unrelated files.
9. Every meaningful change needs a test or verification command.
10. If something is only a candidate, call it candidate-only.

## 6. Next Task

Follow `tasks/NEXT_TASK.md`.

Current intended next work:

Investigate why official detail fetches for `221380`, `221629` and `221675`
captured metadata but no attachment table rows. Keep them candidate-only or
`UNKNOWN` unless separate official status evidence supports a stronger state.

## 7. Update Discipline

After every meaningful update, maintain these files:

### `docs/PROGRESS.md`

Record:

- what changed,
- commands run,
- tests and results,
- coverage numbers,
- limitations,
- current phase/status.

### `docs/DECISIONS.md`

Record only real architectural/product decisions.

Example:

```md
## D-015 - Evaluation rules are editable through UI
**Status:** Accepted

Evaluation rules remain YAML-backed but can be edited through the local UI.
The Python core validates and normalizes the profile before saving.
```

### `docs/HANDOFF.md`

Record overall project state, repo/GitHub access, current verification, what
exists, what is missing and the next gate for a new chat.

### `tasks/NEXT_TASK.md`

Keep this as the next executable task only.

Do not use it as a wishlist.

### `docs/KNOWN_LIMITATIONS.md`

Add limitations proven by real work.

Examples:

- Remote needs `python3.12-venv`.
- ESHIDIS discovery grid is Oracle ADF and remains candidate-only until verification.
- `pypdf` extraction does not cover OCR.

### `README.md`

Update only when the user-facing usage changes:

- new command,
- new UI flow,
- new install step,
- new deployment path.

## 8. Development Model

Do not build this as one large scraper.

Use a pipeline:

```text
source discovery
-> candidate tender
-> official detail fetch
-> attachment listing
-> controlled download
-> document classification
-> text/table extraction
-> search/evaluation rules
-> status verification
-> report/export/UI
```

Each step must leave evidence:

- JSON report,
- Markdown report,
- SQLite records,
- local paths,
- hashes,
- errors.

Rejected, candidate and unknown results are useful. Do not discard them.

## 9. Upgrade Strategy

Classify each future feature before implementing it.

### Source Adapter

Examples:

- ESHIDIS
- KIMDIS
- Diavgeia
- TEE subscription platform
- authority websites

Keep source-specific logic out of the core.

### Document Pipeline

Examples:

- PDF extraction
- OCR
- Excel parser
- DOCX parser
- ZIP extraction
- budget item parser

### Matching / Evaluation

Examples:

- phrases
- CPV
- article codes
- revision codes
- quantities
- unit prices
- score
- severity

These should remain configurable.

### Status Engine

Examples:

- active
- possibly active
- expired
- cancelled
- awarded
- contract signed

Do not mix this with content matching.

### UI / Daily Workflow

The UI should call the audited CLI/core functions, not duplicate business logic.

## 10. Immediate Priority

1. Finish remote setup.
2. Run full tests.
3. Verify selected discovery candidates.
4. Fetch official details.
5. Download/analyze attachments for 2-3 relevant candidates.
6. Run evaluation rules.
7. Update `PROGRESS`, `DECISIONS` if needed, and `NEXT_TASK`.

Do not start a large refactor before the remote environment is verified.
