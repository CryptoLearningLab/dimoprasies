# NEXT TASK

Execute:
`Add clickable email notifications and source skip reporting`

## Current Input

The daily dashboard now loads cached AI triage and uses a fast source
fingerprint preflight before expensive discovery. A live smoke returned
`skipped: true`, `steps: 0` in 4.24s with temporary Diavgeia 503 warnings
instead of running the full discovery pipeline.

Selective non-ESHIDIS refresh now exists: when the preflight identifies a
changed KIMDIS/authority source id, `sources expanded-report` fetches only
that source and retains skipped sources from the previous expanded report.

Noisy decision/context sources removed from active source config:

- Δήμος Αμφιλοχίας - Αποφάσεις Δημάρχου
- Δήμος Αμφιλοχίας - Αποφάσεις Δημοτικού Συμβουλίου
- Δήμος Δωρίδος - Αποφάσεις Επιτροπών source link
- Δήμος Πατρέων - Αποφάσεις Δημοτικής Επιτροπής

## Instruction

Implement the notification/reporting gate:

1. Add email report generation with clickable rows and official ESHIDIS links
   for new/kept rows.
2. Show source preflight status in the UI technical result, including
   `SKIPPED_UNCHANGED`, `SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS`, reachable
   count and warning count.
3. Add per-source skipped/fetched counts to discovery run reports where the
   current data model supports it.
4. Add a separate explicit UI control for full ESHIDIS refresh/backfill so the
   normal daily button can remain selective and fast.
5. Preserve raw reports/provenance, no title-only deduplication, no
    `VERIFIED_ACTIVE` promotion.

## Required Closeout

At the end of the task:

1. Run targeted tests and `.venv/bin/python -m pytest`.
2. Run a bounded live smoke and report skipped/fetched source counts.
3. Update `docs/PROGRESS.md`.
4. Update `docs/DECISIONS.md` only if a real decision was made.
5. Update this file with the next single executable gate.
6. Update `docs/HANDOFF.md` if project state or next gate changed.
7. Commit and push tracked changes to GitHub unless explicitly told not to.
