# NEXT TASK

Execute:
`Persist verified ESHIDIS links and dashboard dedup preference`

## Current Input

The fetched/OCR AI classifier gate is deployed and smoke-tested on the
DigitalOcean droplet.

Final verified state:

- live commit: `ab0d497`;
- UI package version: `0.1.14`;
- `AI_TRIAGE_PROMPT_VERSION`: `2026-07-19-strict-non-works-v2`;
- first v2 AI triage run classified 77 existing dashboard rows in 80.69s;
- second unchanged v2 AI triage run skipped OpenAI in 3.22s;
- final AI report contained 17 kept rows, 60 dropped rows, 12 rows with
  fetched/OCR document evidence, 9 kept rows with linked ESHIDIS ids and
  0 dropped rows with ESHIDIS hints;
- candidate enrichment smoke ran without full discovery: 1 attempted target,
  6 previously skipped attempts, 0 failures, 7.81s.

## Instruction

Implement the next small gate:

1. Add SQLite persistence for official cross-source links from KIMDIS/authority
   rows to verified ESHIDIS ids.
2. Verify candidate ESHIDIS ids through
   `pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{id}`
   before storing them as official links.
3. Do not merge records by title alone.
4. Make the dashboard prefer the official ESHIDIS row when a KIMDIS/authority
   row has a verified ESHIDIS link, while retaining provenance for the original
   KIMDIS/authority source.
5. Keep unverified non-ESHIDIS rows visible as review candidates with a clear
   `NO_VERIFIED_ESHIDIS_LINK` style reason.
6. Add focused tests for:
   - verified link persistence;
   - dashboard replacement/preference;
   - unverified rows remaining visible;
   - no title-only deduplication.

## Required Closeout

1. Run unit tests and full test suite.
2. Run a droplet smoke without full discovery.
3. Report how many rows were replaced by verified ESHIDIS preference and how
   many remain non-ESHIDIS review candidates.
4. Update `docs/PROGRESS.md`.
5. Update `docs/DECISIONS.md` only if a real decision was made.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Update this file with the next single executable gate.
8. Commit and push tracked changes to GitHub unless explicitly told not to.
