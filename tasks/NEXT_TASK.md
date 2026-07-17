# NEXT TASK

Execute:
`Search and evaluate KIMDIS text artifacts`

## Current Input

Use the latest KIMDIS document index:

```text
work/derived/kimdis_open_proc_documents.json
work/extracted_text/kimdis/*.txt
```

Latest KIMDIS document-index result as of `2026-07-17`:

```text
12 SUBMISSION_OPEN_CANDIDATE PROC notices
12 official KIMDIS PDFs present
12 extracted text artifacts
12 records with authority/scope evidence
0 records promoted to VERIFIED_ACTIVE
```

## Instruction

Build the next smallest scoring/search step:

1. Run existing YAML search/evaluation profiles over the KIMDIS extracted text
   artifacts without hardcoding technical phrases in core code.
2. Preserve provenance for every KIMDIS hit: official id, source URL,
   attachment URL, local file path, text path, matched rule/profile and text
   snippet location where available.
3. Produce a combined ESHIDIS/KIMDIS candidate shortlist report.
4. Keep status labels candidate-only:
   `SUBMISSION_OPEN_CANDIDATE` and `ATTACHMENT_*_PENDING_DOCUMENT_REVIEW`.
5. Do not merge repeated titles unless `docs/DEDUPLICATION.md` allows it by
   official identifiers or strong composite evidence.
6. Keep ESHIDIS status verification separate.

Do not store TEE subscription credentials in the repository. Treat TEE as a
future authenticated adapter.

## Required Closeout

At the end of the task:

1. Run the relevant targeted tests and `.venv/bin/python -m pytest` if code
   changed.
2. Update `docs/PROGRESS.md` with exact commands and evidence.
3. Update `docs/DECISIONS.md` only if a real decision was made.
4. Update this file with the next single executable gate.
5. Update `docs/HANDOFF.md` if the project state or next gate changed.
6. Commit and push tracked changes to GitHub unless explicitly told not to.
