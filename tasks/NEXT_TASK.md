# NEXT TASK

Execute:
`Audit rows hidden for missing deadline evidence`

## Current Input

The deadline-evidence dashboard gate is deployed in UI package version
`0.1.19`.

- `dashboard_payload` enriches rows with fetched document evidence before
  active filtering.
- `document_evidence_payload` extracts candidate submission deadlines from
  declaration-like document text, including Greek deadline/offer/extension
  contexts.
- `dashboard_row_is_active` no longer treats unknown deadlines as active.
  Rows without a direct, linked-official or document-derived parseable deadline
  are hidden from the main dashboard.
- Focused local UI tests passed: `tests/test_ui_server.py` -> `92 passed`.
- Full local suite passed: `195 passed`.
- Production smoke on commit `281ff78` passed:
  - homepage contains `v0.1.19`;
  - unauthenticated dashboard API returns `401`;
  - no-discovery dashboard reports `visible 12`, `unknown_visible []`,
    `expired_visible []`, `expired_hidden 74`.

## Instruction

Complete the next gate:

1. Do not run full discovery.
2. Add or expose an audit bucket for rows hidden because no parseable future
   deadline was found.
3. For each hidden row, show whether documents were fetched/OCRed and which
   sources/snippets were checked.
4. Run an incremental/scheduled dry-run only.
5. Confirm the front page still has zero visible unknown-deadline rows.
6. Report how many hidden rows need document fetch/OCR versus how many have
   documents but no deadline evidence.

## Required Tests

- Focused UI/admin audit tests.
- No-discovery dashboard smoke.
- Incremental scheduled dry-run, not full discovery.

## Required Closeout

1. Update `docs/PROGRESS.md` with audit counts and smoke evidence.
2. Update `docs/HANDOFF.md` if production/deployment state changes.
3. Update this file with the next single executable gate.
4. Do not run full discovery unless explicitly requested.
