# NEXT TASK

Execute:
`Implement SQLite FTS-backed reverse content search`

## Current Input

Local version `0.1.32` scaffolds the second tab
`Αντίστροφη αναζήτηση` from `docs/PRODUCT_SPECIFICATION.md`
`MODE B — Αντίστροφη αναζήτηση περιεχομένου`.

Implemented in the current gate:

- A simple product-facing search form in the second tab.
- `/api/reverse-search` as a fast read-only backend route.
- Results are constrained to currently visible active dashboard rows.
- Matching currently checks dashboard metadata, document evidence snippets and
  already extracted ESHIDIS document text from SQLite `documents.text_path` /
  `text_sample`.
- The route does not trigger discovery, source polling, document fetch, OCR,
  AI triage or candidate enrichment.
- Existing one-off technical tools remain collapsed under
  `Εργαλεία συντήρησης`.
- Full local suite passed: `219 passed`.

## Instruction

Complete the next gate:

1. Design a SQLite FTS/index layer for extracted tender document text.
2. Populate/update the index only from already fetched/extracted documents.
3. Keep `/api/reverse-search` read-only and fast; it must not trigger network
   discovery, fetch, OCR or AI.
4. Preserve active-dashboard filtering: results must only include active rows
   that would be visible in the main public-works dashboard.
5. Return provenance-friendly matches: document name/type, snippet, source URL
   or local document handle where available.

## Required Tests

- Focused tests for FTS/index creation and query behavior.
- `tests/test_ui_server.py::test_ui_exposes_reverse_search_tab`.
- `tests/test_ui_server.py::test_reverse_search_payload_searches_active_dashboard_and_documents`.
- Full test suite before production deploy.

## Required Closeout

1. Update `docs/PROGRESS.md` with implementation and smoke evidence.
2. Update `docs/DECISIONS.md` only if the FTS architecture introduces a real
   product/engineering decision.
3. Update `docs/HANDOFF.md` if production/deployment state changes.
4. Update this file with the next single executable gate.
5. Do not run full discovery unless explicitly requested.

## Future Backlog

- Add query grammar: AND, OR, NOT.
- Add filters by document type, deadline window and geography.
- Add article/revision/unit/quantity/price extraction after the text index is
  stable.
- Design a separate nationwide ESHIDIS-only search mode with isolated state,
  explicit limits, no automatic KIMDIS/authority fetch, no automatic OCR/AI,
  and separate audit/reporting.
- Decide whether Diavgeia entalmata need their own email alerts after the first
  live scan confirms data quality.
