# NEXT TASK

Execute:
`Implement source adapters required by whitelist audit`

## Instruction

Use the latest whitelist audit report:

```text
work/reports/source_whitelist_audit.json
work/reports/source_whitelist_audit.md
```

Build the next smallest adapter gate before any expanded search/email report:

1. Inspect `config/sources.yml` and identify the KIMDIS `api_post` entries.
2. Document the required request body, pagination and response fields for one
   KIMDIS family before issuing broad live searches.
3. Implement a conservative audit/fetch adapter for that one family only.
4. Add retry/browser diagnostics for the two failed Patras municipal pages:
   - `https://e-patras.gr/el/tenders`
   - `https://e-patras.gr/el/e-democracy/decisions/municipal-committee-decisions`
5. Re-run `sources audit-whitelist` and record exact results.
6. Keep deduplication aligned with `docs/DEDUPLICATION.md`; never merge records
   by title alone.
7. Do not infer `VERIFIED_ACTIVE` from source presence, content matches or
   repeated titles.

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
