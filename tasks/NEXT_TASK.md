# NEXT TASK

Execute:
`Promote linked ESHIDIS ids into canonical dashboard rows`

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

The next stage is to make linked ESHIDIS ids canonical in the dashboard after
document enrichment finds them.

## Instruction

Implement the linked-ESHIDIS canonicalization gate:

1. When a KIMDIS/authority row has `linked_eshidis_ids`, ensure each id has an
   official ESHIDIS detail fetch attempted.
2. Add or refresh the corresponding ESHIDIS dashboard row from official
   ESHIDIS metadata/files when available.
3. Hide the linked non-ESHIDIS row behind the ESHIDIS row only when the official
   id is present as a real dashboard row; otherwise keep both with clear
   provenance.
4. Preserve raw KIMDIS/authority rows in reports and keep title-only
   deduplication forbidden.
5. Do not promote to `VERIFIED_ACTIVE`; official row means official source, not
   verified active status.

## Required Closeout

At the end of the task:

1. Run targeted tests and `.venv/bin/python -m pytest`.
2. Run a bounded local smoke and report enriched/failed/skipped counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
