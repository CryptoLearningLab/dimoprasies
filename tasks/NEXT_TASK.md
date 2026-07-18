# NEXT TASK

Execute:
`Extend authority discovery adapters beyond e-Patras`

## Current Input

The first municipal/authority discovery path is implemented for:

```text
epatras_tenders
epatras_municipal_committee
```

It feeds `AUTHORITY_DISCOVERY_CANDIDATE` rows into the expanded report and
dashboard. Candidate rows remain candidate-only unless a separate official
status verification proves active tender status.

Use the double-checked source audit supplied on `2026-07-18` as the adapter
blueprint for the next source families:

- WordPress municipal categories:
  - Θέρμο
  - Αμφιλοχία
  - Δωρίδα
  - ΔΕΥΑΠ
  - ΠΣΤΕ via `?rest_route=`
- Μεσολόγγι table page
- PDE regional pages
- Diavgeia API
- TED API

## Instruction

Build the next smallest source-family adapter:

1. Add one generic adapter family at a time.
2. Prefer public JSON/API endpoints over browser scraping where available.
3. Extract normalized candidate records with source URL, detail URL,
   attachment links, publication date, retrieved_at, parser status and explicit
   KIMDIS/ESHIDIS cross-references when present.
4. Do not mark municipal/regional/TED/Diavgeia content matches as active
   tenders.
5. Do not deduplicate by title only.
6. Surface source/fetch/parser failures in the expanded report and UI job
   output.
7. Add targeted tests with mocked HTTP responses before live smoke tests.

Do not scrape behind login, CAPTCHA or non-public access controls.

## Required Closeout

At the end of the task:

1. Run targeted tests for the new adapter and `.venv/bin/python -m pytest`.
2. Update `docs/PROGRESS.md` with exact commands and evidence.
3. Update `docs/DECISIONS.md` only if a real decision was made.
4. Update this file with the next single executable gate.
5. Update `docs/HANDOFF.md` if the project state or next gate changed.
6. Commit and push tracked changes to GitHub unless explicitly told not to.
