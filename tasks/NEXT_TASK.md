# NEXT TASK

Execute:
`Persist and expose fetched KIMDIS PROC attachments`

## Current Input

Use the latest expanded discovery report:

```text
work/reports/expanded_discovery_report.json
work/reports/expanded_discovery_report.md
```

Use the latest KIMDIS attachment fetch report:

```text
work/reports/kimdis_open_proc_fetch_report.json
work/reports/kimdis_open_proc_fetch_report.md
```

Latest KIMDIS fetch result as of `2026-07-17`:

```text
12 SUBMISSION_OPEN_CANDIDATE PROC notices checked
12 official KIMDIS PDFs present under work/download_audit/kimdis/
0 failed fetches
12 documents with text extracted for the shortlist report
12 documents with authority/scope evidence found
0 records promoted to VERIFIED_ACTIVE
```

## Instruction

Build the next smallest integration step:

1. Persist fetched KIMDIS PROC attachment metadata and extracted text in a
   structured model or durable artifact.
2. Preserve official id, title, authority, budget, final submission date,
   source URL, attachment URL, local file path, size, SHA-256 and retrieval
   timestamp.
3. Keep status labels candidate-only:
   `SUBMISSION_OPEN_CANDIDATE` and `ATTACHMENT_*_PENDING_DOCUMENT_REVIEW`.
4. Expose KIMDIS rows in the UI with preview/download actions equivalent to
   ESHIDIS where local files exist.
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
