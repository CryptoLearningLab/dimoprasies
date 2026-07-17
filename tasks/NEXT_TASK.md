# NEXT TASK

Execute:
`Status verification pass for analyzed candidate 221675`

## Instruction

Keep the discovery/status separation:

1. Use existing evidence for `221675`:
   - `work/source_audit/eshidis_resource_audit_221675.json`
   - `work/reports/document_analysis_221675.json`
   - `work/reports/evaluation_public_works_dynamic_221675.json`
   - downloaded attachments under `work/download_audit/`
   - extracted text under `work/extracted_text/`
2. Check the official detail deadline and attachment/document evidence for
   newer acts that could affect status:
   - extension,
   - amendment/correction,
   - cancellation,
   - award/provisional contractor,
   - contract signing,
   - opening/evaluation evidence.
3. Keep `221675` as `UNKNOWN` or candidate-only unless the latest official
   evidence is sufficient for a stronger status.
4. If code is added, keep status verification separate from content matching
   and record provenance for every status finding.
5. Write a JSON/Markdown status-verification report under `work/reports/`.

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
