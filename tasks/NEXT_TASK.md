# NEXT TASK

Execute:
`Run controlled expanded discovery and report pass`

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

Run the next controlled expanded discovery/report pass:

1. Re-run `sources audit-whitelist` at the start and record exact runtime
   failures.
2. Use ESHIDIS `sources discover-active` for active candidates.
3. Use KIMDIS Open Data page-0 probes for PROC/AWRD/SYMV public works
   (`contractType: "10"`) as discovery evidence.
4. Use reachable authority/Diavgeia/DEYAP fallbacks for Patras while the
   municipal site times out.
5. Deduplicate only through `docs/DEDUPLICATION.md`; never merge records by
   title alone.
6. Do not infer `VERIFIED_ACTIVE` from source presence, content matches or
   repeated titles.
7. Produce a JSON/Markdown report artifact suitable for email review before
   sending any email.

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
