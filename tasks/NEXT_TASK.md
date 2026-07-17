# NEXT TASK

Execute:
`Verify expanded KIMDIS focus records`

## Instruction

Use the latest whitelist audit report:

```text
work/reports/source_whitelist_audit.json
work/reports/source_whitelist_audit.md
```

Current source-readiness result:

```text
31 checked, 24 reachable, 3 failed, 0 adapter-required, 4 templates,
2 failed-with-fallback, 0 unresolved blockers
```

Use the latest expanded discovery report:

```text
work/reports/expanded_discovery_report.json
work/reports/expanded_discovery_report.md
```

Latest result:

```text
750 total KIMDIS records, 53 focus-related records, 0 runtime errors
```

Verify and prioritize the focus records:

1. Treat all 53 records as discovery candidates, not `VERIFIED_ACTIVE`.
2. Start from PROC notices because they are most relevant for new/open tender
   discovery.
3. Prefer records with exact authority/location evidence over broad regional or
   alias-only matches.
4. Fetch official KIMDIS attachment URLs for the selected shortlist.
5. Compare repeated titles through `docs/DEDUPLICATION.md`; never merge by title
   alone.
6. Produce a shortlist report with official id, title, authority, budget,
   source URL, attachment URL and verification status.
7. Keep ESHIDIS status verification separate.

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
