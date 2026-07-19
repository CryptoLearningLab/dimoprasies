# NEXT TASK

Execute:
`Audit rows hidden for missing deadline evidence`

## Current Input

The deadline-evidence dashboard gate is deployed and admin audit re-enrichment
is implemented locally in UI package version `0.1.24`.

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
- Admin audit now separates `NO_DEADLINE_EVIDENCE` from real `EXPIRED` rows.
- Focused admin/UI tests passed: `93 passed`.
- Admin audit re-enrichment adds `DUPLICATE_CANDIDATE` for strong unverified
  matches against existing official ESHIDIS rows.
- The Μεσολόγγι gymnasium authority row now maps as candidate duplicate to
  ESHIDIS `221624` in local smoke.
- Admin hidden rows are mobile responsive via `data-label` card layout.
- Admin users now expose/display SQLite `id` and use a mobile-card responsive
  layout.
- Admins can update bounded user roles (`admin`, `tester`, `user`) by email or
  displayed `#ID`. The main source polling audit is hidden from the daily front
  page and tender pills wrap cleanly on mobile.
- Mobile tender cards reserve enough label width for `Προϋπολογισμός`. Admin
  hidden rows are grouped by rejection category, not chronological order.

## Instruction

Complete the next gate:

1. Do not run full discovery.
2. Run an incremental/scheduled dry-run only.
3. Confirm the front page still has zero visible unknown-deadline rows.
4. Review remaining `NO_DEADLINE_EVIDENCE` rows that are not
   `DUPLICATE_CANDIDATE`.
5. Report how many need document fetch/OCR versus deeper source/title search.

## Required Tests

- Focused UI/admin audit tests.
- No-discovery dashboard smoke.
- Incremental scheduled dry-run, not full discovery.

## Required Closeout

1. Update `docs/PROGRESS.md` with audit counts and smoke evidence.
2. Update `docs/HANDOFF.md` if production/deployment state changes.
3. Update this file with the next single executable gate.
4. Do not run full discovery unless explicitly requested.
