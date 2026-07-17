# NEXT TASK

Execute:
`Fetch and verify open KIMDIS PROC candidates`

## Instruction

Use the latest whitelist audit report:

```text
work/reports/source_whitelist_audit.json
work/reports/source_whitelist_audit.md
```

Current source-readiness result:

```text
36 checked, 29 reachable/ready, 3 failed, 0 adapter-required, 4 templates,
2 failed-with-fallback, 0 unresolved blockers
```

Use the latest expanded discovery report:

```text
work/reports/expanded_discovery_report.json
work/reports/expanded_discovery_report.md
```

Latest result as of `2026-07-17`:

```text
765 total records
51 focus-related records
12 SUBMISSION_OPEN_CANDIDATE PROC notices
0 focus-expired PROC notices
37 historical AWRD/SYMV records
0 runtime errors
```

Fetch and verify the open PROC records:

1. Treat the 12 open PROC records as `SUBMISSION_OPEN_CANDIDATE`, not
   `VERIFIED_ACTIVE`.
2. Fetch official KIMDIS attachment URLs for those 12 PROC ids.
3. Extract or inspect the attachments for exact place/authority evidence.
4. Compare related/cancelled notice pairs through `docs/DEDUPLICATION.md`;
   never merge by title alone.
5. Produce a shortlist report with official id, title, authority, budget,
   final submission date, source URL, attachment URL, local file metadata and
   verification status.
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
