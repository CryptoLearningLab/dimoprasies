# NEXT TASK

Execute:
`Production-smoke fetched/OCR AI classifier results`

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

The AI classifier now consumes fetched/OCR document evidence for pending rows.
The next product gate is to run a production smoke, inspect exactly what the AI
kept/dropped and tighten only observed prompt/classifier failures.

## Instruction

Implement the next small gate:

1. Deploy `v0.1.14`.
2. Run one live AI triage/enrichment smoke on the droplet without forcing full
   discovery.
3. Inspect `work/reports/ai_triage_report.json` and the dashboard summary.
4. List rows kept, dropped and linked to ESHIDIS by the new document evidence.
5. Record any concrete false keep/drop with provenance.
6. Only if there is a concrete failure, tighten the prompt/classifier and add a
   focused regression test.

## Required Closeout

1. Run droplet AI triage/enrichment smoke and record elapsed time.
2. Confirm unchanged sources do not trigger full discovery.
3. Confirm document evidence appears for changed/pending rows where local
   fetched/OCR text exists.
4. Report changed files and verification commands.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
