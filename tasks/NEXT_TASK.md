# NEXT TASK

Execute:
`Add source watermark skip and clickable email notifications`

## Current Input

The daily dashboard now loads cached AI triage and shows 39 focus rows by
default, hiding 89 `DROP_*` rows from the main workflow while preserving raw
reports/provenance.

Noisy decision/context sources removed from active source config:

- Δήμος Αμφιλοχίας - Αποφάσεις Δημάρχου
- Δήμος Αμφιλοχίας - Αποφάσεις Δημοτικού Συμβουλίου
- Δήμος Δωρίδος - Αποφάσεις Επιτροπών source link
- Δήμος Πατρέων - Αποφάσεις Δημοτικής Επιτροπής

## Instruction

Implement the performance/notification gate:

1. Add per-source cheap-change watermarks under `work/derived/`.
2. For WordPress sources, check latest `id/date` with `per_page=1` before
   full fetch.
3. For Diavgeia sources, check latest `ada/submissionTimestamp` with `size=1`
   before full fetch.
4. For TED, check latest publication token/date before full fetch.
5. For KIMDIS, stop page scanning when known `referenceNumber` appears.
6. For HTML/Drupal sources, use `ETag`/`Last-Modified` if available, otherwise
   hash the first listing page.
7. Do not update a watermark after a failed or partial source run.
8. Keep unchanged sources visible in run reports as `SKIPPED_UNCHANGED`.
9. Add email report generation with clickable rows and official ESHIDIS links
   for new/kept rows.
10. Preserve raw reports/provenance, no title-only deduplication, no
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
