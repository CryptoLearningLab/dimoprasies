# Decision Log

## D-001 — Repo-native knowledge
**Status:** Accepted

Η μόνιμη γνώση αποθηκεύεται σε `AGENTS.md`, `docs/`, configuration
και task files. Δεν βασίζεται στη μνήμη του chat.

## D-002 — One phase per task
**Status:** Accepted

Κάθε Codex task εκτελεί μία φάση ή σαφές milestone.
Η συνέχεια γράφεται στο `tasks/NEXT_TASK.md`.

## D-003 — Generic core, profile-specific searches
**Status:** Accepted

Ο πυρήνας είναι ουδέτερος ως προς τεχνικές κατηγορίες.
Οι ειδικοί όροι και κωδικοί μπαίνουν σε YAML profiles.

## D-004 — Content and status separation
**Status:** Accepted

Η εύρεση τεχνικής φράσης δεν αποδεικνύει ενεργό διαγωνισμό.
Το status verification είναι ανεξάρτητο pipeline.

## D-005 — Dependency-light bootstrap
**Status:** Accepted

Το Phase 0 υλοποιείται με standard-library CLI, logging και fallback YAML
loader, ώστε το εργαλείο να έχει καθαρή ελάχιστη εκκίνηση. Το PyYAML
παραμένει προτεινόμενο dev/yaml dependency για πλήρη YAML συμβατότητα.

## D-006 — Source commands disabled before audit
**Status:** Accepted

Οι εντολές `scan`, `download`, `search`, `export` και `status-check`
υπάρχουν ως CLI placeholders αλλά αποτυγχάνουν σκόπιμα μέχρι να ολοκληρωθεί
το source audit της PHASE 1.

## D-007 — Browser-required ESHIDIS entry point
**Status:** Accepted

Η δημόσια αναζήτηση έργων ΕΣΗΔΗΣ αντιμετωπίζεται ως Oracle ADF browser/session
ροή. Δεν θεωρείται σταθερό direct HTTP API μέχρι να αποδειχθεί με network
inspection.

## D-008 — TLS audit fallback only
**Status:** Accepted

Το `--allow-insecure-tls` επιτρέπεται μόνο για διαγνωστικό source audit.
Η παραγωγική ανάκτηση πρέπει να χρησιμοποιεί σωστή αλυσίδα εμπιστοσύνης
πιστοποιητικών.

## D-009 — Authority pages as discovery evidence
**Status:** Accepted

Οι δημόσιες σελίδες φορέων μπορούν να χρησιμοποιηθούν για discovery και
fallback συνημμένα, αλλά δεν αντικαθιστούν επίσημη επαλήθευση κατάστασης
από ΕΣΗΔΗΣ/ΚΗΜΔΗΣ ή νεότερες επίσημες πράξεις.

## D-010 — Playwright audit before production adapter
**Status:** Accepted

Το Playwright χρησιμοποιείται ως εργαλείο audit για τη δημόσια Oracle ADF ροή
ΕΣΗΔΗΣ. Δεν ενεργοποιείται παραγωγικό `scan` μέχρι να αποδειχθεί επαναλήψιμη
ανάκτηση ορατής επίσημης γραμμής και official attachment listing.

## D-011 — Direct ESHIDIS resource as first adapter target
**Status:** Accepted

Το `resources/search/{eshidis_id}` είναι το πρώτο πρακτικό public-source target
για read-only adapter, επειδή απέδωσε επίσημη σελίδα detail και attachment
listing χωρίς login για τον διαγωνισμό `221744`.

## D-012 — TEE subscription source as future authenticated adapter
**Status:** Accepted

Η συνδρομητική πλατφόρμα ΤΕΕ θα αξιολογηθεί ως πρόσθετη πηγή discovery/status.
Οι κωδικοί δεν αποθηκεύονται σε repository files και θα χρησιμοποιηθούν μόνο
μέσω ασφαλούς runtime εισαγωγής ή local secret store.

## D-013 - Attachment downloads are audited before bulk use
**Status:** Accepted

## D-014 - ESHIDIS grid discovery stays candidate-only
**Status:** Accepted

The public ESHIDIS active-search grid may expose tender rows only inside
Oracle ADF XML responses, not as stable visible DOM rows. `sources
discover-active` may parse those rows as `DISCOVERED_ACTIVE_CANDIDATE`, but
each id must still be verified through `resources/search/{eshidis_id}` before
the project uses `VERIFIED_ACTIVE`.

Το `Λήψη` του ΕΣΗΔΗΣ περνά πρώτα από single-row browser audit πριν γίνει
παραγωγική εντολή download. Κάθε αποθηκευμένο αρχείο πρέπει να κρατά local path,
μέγεθος, SHA-256 και χρόνο ανάκτησης στη SQLite βάση.

## D-015 - ESHIDIS resource import may be metadata-only
**Status:** Accepted

When an official `resources/search/{eshidis_id}` fetch returns tender detail
metadata but no parsable attachment table response, the CLI imports the tender
metadata and records `attachment_rows: null` with zero imported attachments.
This is not treated as successful attachment listing and must remain visible in
progress reports before any download/analyze step.
