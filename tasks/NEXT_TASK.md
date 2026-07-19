# NEXT TASK

Execute:
`Design and scaffold reverse content search tab`

## Current Input

The deadline-evidence dashboard gate is deployed and admin audit re-enrichment
is implemented. Nationwide search is disabled in production version `0.1.26`.
Production version `0.1.30` fixes PDF-body text matching parity with the
Windows `.exe` and adds paginated Diavgeia scan. Local version `0.1.31`
polishes the entalmata UI, adds local retained PDF links, adds deterministic
project-title extraction and exposes a CLI-only `--max-pages` deep scan
override.

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
- Mobile tender cards reserve enough label width for `Προϋπολογισμός`.
- Admin hidden rows are sorted by most recent audit event first and expose the
  audit timestamp in the admin panel, with source epoch timestamps normalized
  to ISO UTC. Deterministic audit rows persist first-hidden timestamps in
  SQLite `admin_hidden_events`.
- Nationwide search is disabled in the user-facing product. It remains a
  future expansion only, after the local workflow is stable and a separate
  ESHIDIS-only/mode-aware design is approved.
- The former `Αρχεία` tab is replaced locally by `Εντάλματα`.
- `config/diavgeia_entalmata.yml` configures the Diavgeia search endpoint,
  organizations `14722` and `50051`, the 15-day visible window and keyword
  matching.
- `tender-radar entalmata scan` stores matches in SQLite table
  `diavgeia_entalmata`, downloads evidence under
  `work/download_audit/diavgeia_entalmata`, and archives old visible files
  under `work/download_audit/diavgeia_entalmata/old`.
- Production scan on commit `ec5aa13` checked `80` Diavgeia decisions across
  the two configured organizations with `errors 0`; none matched the current
  six keywords, so the UI correctly shows `0` visible entalmata and SQLite has
  `80` `REJECTED` rows.
- Follow-up inspection found this was not a source/filter problem: PDFs were
  downloaded, but the integrated extractor used only `fitz` and returned empty
  text when PyMuPDF was absent. Local `v0.1.29` falls back to the shared
  `pypdf`/OCR extractor and adds PyMuPDF to the deploy dependency group.
- Follow-up pagination checks found protocol `1569` on `14722` page `1` and
  protocol `1739` on `50051` page `4`, so the entalmata config now checks up
  to `8` pages per organization.
- Production deploy on commit `334b1ef` passed: package version `0.1.30`,
  homepage `v0.1.30`, `fitz` and `pypdf` installed. A bounded live Diavgeia
  entalmata scan checked `240` decisions across `6` pages, found `5` visible
  matches (`1793`, `1739`, `1720`, `1569`, `1737`), rejected `109`, marked
  `126` outside the 15-day window and completed with `errors 0`.
- Local `v0.1.31` adds the requested nav order, entalmata PDF actions,
  archived count, project-title extraction and CLI-only deep-scan override.
- Product spec `MODE B — Αντίστροφη αναζήτηση περιεχομένου` defines the
  intended second tab: phrase/word/article/revision/material/unit/quantity/price
  search over extracted tender document content with document and time filters.

## Instruction

Complete the next gate:

1. Deploy and smoke `v0.1.31`.
2. Run one explicit production `entalmata scan --max-pages 100` and report
   visible/archived/error counts without changing the normal UI scan depth.
3. Read `docs/PRODUCT_SPECIFICATION.md` Mode B and existing search/index
   mechanisms.
4. Scaffold the second tab as `Αντίστροφη αναζήτηση` with a minimal request
   form and empty-state result surface.
5. Do not implement expensive full-document search until the UI contract and
   backend query path are confirmed.

## Required Tests

- `tests/test_entalmata.py`.
- `tests/test_ui_server.py::test_ui_exposes_entalmata_tab`.
- `tests/test_cli.py::CliTests::test_entalmata_scan_parser_has_safe_defaults`.
- Full test suite before production deploy.

## Required Closeout

1. Update `docs/PROGRESS.md` with implementation and smoke evidence.
2. Update `docs/HANDOFF.md` if production/deployment state changes.
3. Update this file with the next single executable gate.
4. Do not run full discovery unless explicitly requested.

## Future Backlog

- Design a separate nationwide ESHIDIS-only search mode with isolated state,
  explicit limits, no automatic KIMDIS/authority fetch, no automatic OCR/AI,
  and separate audit/reporting.
- Decide whether Diavgeia entalmata need their own email alerts after the first
  live scan confirms data quality.
