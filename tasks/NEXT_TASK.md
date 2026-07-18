# NEXT TASK

Execute:
`Add non-ESHIDIS document enrichment to find official ESHIDIS ids`

## Current Input

The daily dashboard now uses source fingerprint preflight, selective
non-ESHIDIS refresh and canonical ESHIDIS duplicate suppression.
The preflight counts all configured source entries: 31 configured entries in
the current `config/sources.yml`, 27 directly attempted endpoints and 4
identifier templates.
Changed `eshidis_active_search`, KIMDIS families and authority adapters now use
delta refresh orchestration; unchanged source rows are retained from the
previous report instead of forcing full discovery.
Discovery rows now pass a deterministic public-works gate before the dashboard
daily list: ESHIDIS rows are kept as official public-works rows, while KIMDIS
and authority rows are filtered or kept with `public_works_gate` reasons.

Generic PDE landing rows such as `Έργα & Δράσεις` /
`https://pde.gov.gr/el/erga-drasis/` are excluded from the dashboard.
Authority rows surface deterministic `linked_eshidis_ids` when their cached
text or URLs contain guarded ESHIDIS references.

ESHIDIS id extraction is context-first: official resource URLs and article
`2.2` style references use 6-digit primary ids, `ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ
ΠΡΟΣΦΟΡΑΣ` can expose `Α/Α ΣΥΣΤΗΜΑΤΟΣ`, and broad 7-digit matching is removed.

The next stage is to treat ESHIDIS as the only official tender authority and
enrich every non-ESHIDIS kept candidate by downloading available documents and
extracting/searching for a linked ESHIDIS id.

## Instruction

Implement the non-ESHIDIS document enrichment gate:

1. For each kept KIMDIS/authority row, fetch available public documents first
   when attachment URLs exist.
2. Extract ESHIDIS ids deterministically from article `2.2`,
   `resources/search/<id>`, guarded `Α/Α Διαγωνισμού`, and
   `ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ` / `Α/Α ΣΥΣΤΗΜΑΤΟΣ`.
3. Add an optional exact-title public search enrichment step only when it can
   record source URL, retrieved-at time and evidence snippet.
4. When an ESHIDIS id is found, fetch the official ESHIDIS detail/folder and
   surface the row as linked to that official id.
5. If no ESHIDIS id is found, keep the KIMDIS/authority link with a visible
   note that no official ESHIDIS id was found.
6. Use a background/progress job with partial JSON writes if any enrichment can
   run long.
7. Preserve raw reports/provenance, no title-only deduplication, no
   `VERIFIED_ACTIVE` promotion.

## Required Closeout

At the end of the task:

1. Run targeted tests and `.venv/bin/python -m pytest`.
2. Run a bounded local smoke and report enriched/failed/skipped counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
