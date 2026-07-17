# Implementation Phases and Acceptance Gates

## Γενικός κανόνας

Μία φάση ανά Codex task.

Η επόμενη φάση ξεκινά μόνο όταν:

1. εκτελέστηκαν tests,
2. υπάρχουν παρατηρήσιμα αποδεικτικά,
3. ενημερώθηκε το `docs/PROGRESS.md`,
4. καταγράφηκαν ανοιχτά προβλήματα,
5. γράφτηκε το `tasks/NEXT_TASK.md`.

## PHASE 0 — Repository Bootstrap

Παραδοτέα:
- repository audit,
- Python skeleton,
- configuration loader,
- logging,
- test runner,
- schema draft,
- README,
- environment validation.

Gate:
- clean install,
- `pytest` εκτελείται,
- CLI help λειτουργεί,
- καμία source integration δεν παρουσιάζεται ως έτοιμη.

## PHASE 1 — Source Audit and Retrieval Proof

Παραδοτέα:
- `docs/SOURCE_AUDIT.md`,
- health checks,
- adapter proof,
- endpoint/browser strategy,
- listing πραγματικού tender και attachments.

Gate:
- επαναλήψιμη ανάκτηση ενός tender,
- attachment listing ή τεκμηριωμένος blocker,
- χωρίς ιδιωτικό login,
- tests adapter contract.

## PHASE 2 — End-to-End Vertical Slice

Αλυσίδα:
discover → metadata → status → attachments → download
→ classify → parse → search → database → Excel.

Gate:
- fixture ανακτάται,
- PDF αναλύεται με σελίδα,
- budget item εξάγεται,
- SearchRequest επιστρέφει hit,
- hit αποθηκεύεται και εξάγεται,
- provenance και errors υπάρχουν.

## PHASE 3 — Geographic MVP

Gate:
- pagination,
- geography matching,
- status verification,
- active/candidate/rejected χωριστά,
- `active_tenders.xlsx`,
- coverage summary.

## PHASE 4 — Document Pipeline

Gate:
- αντιπροσωπευτικό corpus,
- κάθε failure ταξινομείται,
- OCR μόνο ως fallback,
- originals immutable,
- page/sheet/row provenance.

## PHASE 5 — Generic Reverse Search

Gate:
- SearchRequest validation,
- exact/morphological/strong-related/semantic modes,
- document και numeric filters,
- generic profile loader,
- rockfall profile χωρίς hardcoding,
- `reverse_search_results.xlsx`.

## PHASE 6 — Change Detection and History

Gate:
- νέα/αλλαγμένα attachments,
- status transitions,
- deadline changes,
- version history,
- rejection reuse,
- `status_changes.xlsx`,
- idempotent rerun.

## PHASE 7 — Hardening, Scheduling and Dashboard

Gate:
- retries/backoff,
- health monitoring,
- safe scheduling,
- dashboard/report,
- runbook,
- backup/restore,
- metrics,
- manual review queue,
- γνωστοί περιορισμοί.
