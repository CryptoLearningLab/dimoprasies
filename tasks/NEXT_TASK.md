# NEXT TASK

Execute:
`Add OCR fallback for scanned fetched documents`

## Current Input

The document fetcher gate is complete for authority/municipal/regional rows:

- non-ESHIDIS fetched document provenance is persisted in SQLite
  `source_documents`;
- unchanged authority documents are reused instead of re-downloaded;
- ESHIDIS official attachment downloads keep using the existing
  `attachments` table and skip behavior;
- KIMDIS has an existing JSON document-index bridge and local-file skip
  behavior.

The next product gate is text extraction/OCR. Existing document analysis can
extract embedded text from supported PDFs and documents, but scanned PDFs or
image-only files may produce weak or empty text. Those weak extractions reduce
the AI classifier's ability to find ESHIDIS ids, deadlines and tender status
evidence.

## Instruction

Implement the next small gate:

1. Inspect the current text extraction path in `src/tender_radar/documents.py`
   and the document analysis CLI/UI callers.
2. Define a deterministic "needs OCR" condition for fetched files:
   - empty extracted text,
   - very short extracted text,
   - extraction error,
   - image-only PDF/page signal when available.
3. Add an OCR fallback behind an optional runtime dependency or available
   system tool. Do not make the app fail when OCR tooling is missing.
4. Persist OCR status and errors in document analysis outputs/provenance.
5. Keep originals untouched.
6. Add focused tests for:
   - normal text extraction does not run OCR;
   - weak/empty extraction attempts OCR when tooling is available;
   - missing OCR tooling records a visible non-fatal error.

## Required Closeout

1. Run targeted OCR/document tests.
2. Run the full test suite if app code changes.
3. Run one droplet smoke on a known scanned/weak document if available; if not
   available, report the gap explicitly.
4. Report changed files and verification commands.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
