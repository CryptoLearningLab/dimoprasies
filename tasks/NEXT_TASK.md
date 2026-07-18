# NEXT TASK

Execute:
`Add municipal and authority website discovery adapters`

## Current Input

Use the configured authority sources in:

```text
config/sources.yml
docs/SOURCE_WHITELIST.md
work/reports/source_whitelist_audit_latest.json
```

Latest source whitelist audit as of `2026-07-18`:

```text
36 sources checked
31 reachable
1 failed
4 templates
0 adapter-required in the audit classification
0 unresolved blockers
e-Patras tender page reachable
e-Patras municipal committee decisions page reachable
```

## Instruction

Build the next smallest source-coverage step:

1. Add a municipal/authority website discovery adapter abstraction for public
   HTML listing pages.
2. Start with e-Patras:
   - `https://e-patras.gr/el/tenders`
   - `https://e-patras.gr/el/e-democracy/decisions/municipal-committee-decisions`
3. Extract normalized candidate records with source URL, title, authority/scope,
   publication date where available, attachment/detail links, retrieved_at and
   parser status.
4. Keep records candidate-only. Do not promote to `VERIFIED_ACTIVE`.
5. Route extracted candidates through the existing dashboard/dedup/provenance
   path without title-only deduplication.
6. Surface parser/fetch failures in reports and UI/job output.

Do not scrape behind login, CAPTCHA or non-public access controls.

## Required Closeout

At the end of the task:

1. Run targeted tests for the new adapter and `.venv/bin/python -m pytest` if
   code changed.
2. Update `docs/PROGRESS.md` with exact commands and evidence.
3. Update `docs/DECISIONS.md` only if a real decision was made.
4. Update this file with the next single executable gate.
5. Update `docs/HANDOFF.md` if the project state or next gate changed.
6. Commit and push tracked changes to GitHub unless explicitly told not to.
