# NEXT TASK

Execute:
`Feed fetched/OCR text into AI classifier and ESHIDIS-id resolution`

## Current Input

The document fetcher and first OCR fallback gates are complete:

- scheduled runs can automatically fetch documents for new/changed
  non-ESHIDIS rows before presentation;
- non-ESHIDIS fetched document provenance is persisted in SQLite
  `source_documents`;
- unchanged authority documents are reused instead of re-downloaded;
- ESHIDIS official attachment downloads keep using the existing
  `attachments` table and skip behavior;
- KIMDIS has an existing JSON document-index bridge and local-file skip
  behavior;
- document analysis now records `ocr_status` and `ocr_error`;
- weak PDF extraction attempts bounded OCR when `pdftoppm` and `tesseract`
  are available and records non-fatal missing-tool errors otherwise;
- the UI has an `Admin panel` tab for auditing hidden rows and restoring AI
  false drops or accidental `Δεν με ενδιαφέρει` dismissals. Restores are stored
  as SQLite `triage_overrides` feedback.
- the UI is private-by-default as of `v0.1.13`: users must log in with
  SQLite invite/password credentials before dashboard/action APIs are
  available, and only `admin` role sessions can access audit/restore/invite
  controls.

The next product gate is to make the AI classifier consume the fetched/OCR
document text for candidate triage and ESHIDIS-id resolution, instead of relying
only on listing/title metadata.

## Instruction

Implement the next small gate:

1. Inspect current AI triage prompt/payload creation and candidate enrichment
   outputs.
2. Add document text snippets/evidence from fetched authority/KIMDIS documents
   to AI triage payloads for rows that have local documents.
3. Include OCR provenance in that payload so weak/no-OCR cases remain visible.
4. Keep AI calls incremental: do not resend already-triaged unchanged rows.
5. Extract linked ESHIDIS ids from OCR-enhanced text before sending to AI where
   deterministic extraction already succeeds.
6. Add focused tests for:
   - document text is included for untriaged rows with fetched files;
   - rows with linked ESHIDIS ids are upgraded/deduped without an extra full
     discovery;
   - already-triaged unchanged rows do not call OpenAI again.

## Required Closeout

1. Run targeted AI/document triage tests.
2. Run the full test suite if app code changes.
3. Run one droplet scheduled-run dry-run or UI search smoke proving unchanged
   sources remain fast and document text is available for changed rows.
4. Report changed files and verification commands.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
