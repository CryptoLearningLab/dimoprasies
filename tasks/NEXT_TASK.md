# NEXT TASK

Execute:
`Deploy tightened AI classifier and verify official ESHIDIS linking`

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

The AI classifier consumes fetched/OCR document evidence for pending rows.
Production smoke confirmed that signature-based caching works: the first run
after adding signatures classified 77 rows, and the second unchanged run skipped
AI in a few seconds. The live report exposed concrete false keeps for
technical-consultant services, direct assignments and supply/installation rows;
the prompt was tightened and `AI_TRIAGE_PROMPT_VERSION` was added to the cache
signature.

## Instruction

Implement the next small gate:

1. Deploy the tightened prompt/signature update.
2. Rerun live AI triage on the droplet without forcing full discovery.
3. Confirm the prompt-version change invalidates old cached decisions once.
4. Confirm the next unchanged run skips AI again.
5. Inspect `work/reports/ai_triage_report.json` for remaining false keeps or
   false drops.
6. Run candidate enrichment for linked ESHIDIS ids with a time budget and list
   which ids verified or failed.
7. If linked ESHIDIS candidates verify successfully, prepare the next persistence
   gate for storing official ESHIDIS replacements/dedup relations in SQLite.

## Required Closeout

1. Run droplet AI triage/enrichment smoke and record elapsed time.
2. Confirm unchanged sources do not trigger full discovery.
3. Confirm prompt-version invalidation and unchanged-row skip both work.
4. Confirm document evidence appears for changed/pending rows where local
   fetched/OCR text exists.
5. Report changed files and verification commands.
6. Update `docs/PROGRESS.md`.
7. Update `docs/DECISIONS.md` only if a real decision was made.
8. Update this file with the next single executable gate.
9. Update `docs/HANDOFF.md` if project state or next gate changed.
10. Commit and push tracked changes to GitHub unless explicitly told not to.
