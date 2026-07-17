# NEXT TASK

Execute:
`Manual review of redesigned UI, then candidate 221629 document gate`

## Instruction

First manually review the redesigned UI first screen:

1. Start the UI:
   - `.venv/bin/tender-radar-ui --host 0.0.0.0 --port 8765`
2. Open the UI from a browser and check:
   - default local-interest scope,
   - all-Greece toggle,
   - essential tender table,
   - official ESHIDIS links,
   - `Download files`,
   - preview for declaration, technical description and budget.
3. Confirm that the UI does not claim `VERIFIED_ACTIVE` or national
   completeness.

Then continue the document gate for `221629`:

1. Use existing evidence for `221629`:
   - `work/source_audit/eshidis_resource_audit_221629.json`
   - SQLite latest attachment rows for ESHIDIS id `221629`
2. Run controlled bulk download:
   - `.venv/bin/python -m tender_radar sources download-attachment 221629 --all --limit 20 --allow-insecure-tls`
3. Run document analysis with JSON/Markdown reports:
   - `.venv/bin/python -m tender_radar documents analyze --eshidis-id 221629 --report work/reports/document_analysis_221629.json --markdown-report work/reports/document_analysis_221629.md`
4. Run dynamic evaluation:
   - `.venv/bin/python -m tender_radar evaluate run --profile config/evaluation_profiles/public_works_dynamic.yml --eshidis-id 221629 --report work/reports/evaluation_public_works_dynamic_221629.json --markdown-report work/reports/evaluation_public_works_dynamic_221629.md`
5. Do not infer `VERIFIED_ACTIVE` from content matches. Status verification
   remains a separate command/gate.

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
