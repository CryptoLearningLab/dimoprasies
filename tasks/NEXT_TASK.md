# NEXT TASK

Execute:
`Add AI/document enrichment progress job`

## Current Input

The daily dashboard now uses source fingerprint preflight, selective
non-ESHIDIS refresh and canonical ESHIDIS duplicate suppression.
The preflight counts all configured source entries: 31 configured entries in
the current `config/sources.yml`, 27 directly attempted endpoints and 4
identifier templates.
Changed `eshidis_active_search`, KIMDIS families and authority adapters now use
delta refresh orchestration; unchanged source rows are retained from the
previous report instead of forcing full discovery.

Generic PDE landing rows such as `Έργα & Δράσεις` /
`https://pde.gov.gr/el/erga-drasis/` are excluded from the dashboard.
Authority rows surface deterministic `linked_eshidis_ids` when their cached
text or URLs contain guarded ESHIDIS references.

ESHIDIS id extraction is context-first: official resource URLs and article
`2.2` style references use 6-digit primary ids, `ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ
ΠΡΟΣΦΟΡΑΣ` can expose `Α/Α ΣΥΣΤΗΜΑΤΟΣ`, and broad 7-digit matching is removed.

The AI prompt now knows about article `2.2` and economic-offer-form contexts.
A single-row AI smoke succeeded, but full-list AI refresh stayed blocked inside
an OpenAI HTTPS response until interrupted. It must not be exposed as a silent
long UI action.

## Instruction

Implement the AI/document enrichment gate:

1. Add a background job for AI/document enrichment with batch-level progress
   and partial JSON writes, so a slow OpenAI/source request does not lose all
   completed work.
2. For each visible/candidate row, fetch available authority/KIMDIS documents
   first when public attachment URLs exist.
3. Extract ESHIDIS ids deterministically from article `2.2`,
   `resources/search/<id>`, guarded `Α/Α Διαγωνισμού`, and
   `ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ` / `Α/Α ΣΥΣΤΗΜΑΤΟΣ`.
4. Add an optional exact-title public search enrichment step only when it can
   record source URL, retrieved-at time and evidence snippet.
5. Write refreshed `linked_eshidis_ids` / `ai_triage_report` caches and surface
   the ids visibly in the dashboard.
6. Preserve raw reports/provenance, no title-only deduplication, no
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
