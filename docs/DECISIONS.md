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

Το `Λήψη` του ΕΣΗΔΗΣ περνά πρώτα από single-row browser audit πριν γίνει
παραγωγική εντολή download. Κάθε αποθηκευμένο αρχείο πρέπει να κρατά local path,
μέγεθος, SHA-256 και χρόνο ανάκτησης στη SQLite βάση.

## D-014 - ESHIDIS grid discovery stays candidate-only
**Status:** Accepted

The public ESHIDIS active-search grid may expose tender rows only inside
Oracle ADF XML responses, not as stable visible DOM rows. `sources
discover-active` may parse those rows as `DISCOVERED_ACTIVE_CANDIDATE`, but
each id must still be verified through `resources/search/{eshidis_id}` before
the project uses `VERIFIED_ACTIVE`.

## D-015 - ESHIDIS resource import may be metadata-only
**Status:** Accepted

When an official `resources/search/{eshidis_id}` fetch returns tender detail
metadata but no parsable attachment table response, the CLI imports the tender
metadata and records `attachment_rows: null` with zero imported attachments.
This is not treated as successful attachment listing and must remain visible in
progress reports before any download/analyze step.

## D-016 - GitHub is the shared project snapshot
**Status:** Accepted

Tracked code, configuration, docs, task files and tests are pushed to
`CryptoLearningLab/dimoprasies` so the user can inspect the current project
state from GitHub. Runtime artifacts remain out of git unless deliberately
curated into docs or fixtures.

Ignored runtime artifacts include `.venv/`, caches, `data/`, `work/`,
`archive/`, generated reports and zip snapshots.

## D-017 - Dedicated deploy key per repository
**Status:** Accepted

Codex access to `CryptoLearningLab/dimoprasies` uses the repository-specific
deploy key `dimoprasies-codex`. Keys from other projects must not be reused.
If the GitHub repo becomes private, this key should remain installed with
write access when Codex is expected to push updates.

## D-018 - Temporary UI tunnels are preview-only
**Status:** Accepted

Public tunnel links may be used for short manual UI previews, but they are not
stable deployment. Daily operation should use local access, LAN/Tailscale, or
the documented Synology/container path.

## D-019 - Status verification reports are advisory before persistence
**Status:** Accepted

`status verify` writes JSON/Markdown evidence with `recommended_status`,
confidence, rationale and status signals, but it does not mutate
`tenders.status`. Persisted status transitions require a separate status
history/persistence model. Until then, even a future official deadline is
reported as advisory `POSSIBLY_ACTIVE`, not `VERIFIED_ACTIVE`.

## D-020 - Human UI composes existing mechanisms
**Status:** Accepted

The business-facing UI presents a focused tender list and document preview, but
it remains a composition layer over the existing CLI/source/database
mechanisms. Geographic focus is loaded from `config/locations.yml`. The
all-Greece toggle changes presentation scope only and must not imply national
coverage completeness.

## D-021 - Source whitelist is configuration, not coverage proof
**Status:** Accepted

The uploaded source whitelist is stored in `config/sources.yml` and
`docs/SOURCE_WHITELIST.md`. It defines source families and priority order, but
it is not treated as completed coverage until each source has a documented
accessibility and behavior audit with visible failures.

## D-022 - Deduplication requires official identifiers or strong evidence
**Status:** Accepted

Tender records must not be merged by title alone. Deduplication follows
`docs/DEDUPLICATION.md`: exact source identifiers and official
cross-references are strongest; ambiguous cases stay separate and may be linked
as `POSSIBLY_RELATED`.

## D-023 - Source failures are separated from adapter blockers
**Status:** Accepted

Whitelist audit results distinguish missing adapters from runtime source
availability. A source timeout is recorded as a failure, but it is not an
adapter blocker when a known adapter can retry it or when another configured
source for the same scope is reachable. URL templates are treated as ready once
their official identifier is known.

## D-024 - Ambiguous place aliases are recall-first
**Status:** Accepted

Ambiguous place names are not silently discarded when they may refer to a focus
area. Configuration may define `ambiguous_aliases` with positive and negative
context. A negative context such as another municipality, region or NUTS code
blocks the match. A positive context confirms it. If the alias appears without
either, the candidate is retained for human review with a match note rather
than being filtered out.

## D-025 - Dashboard rows own document actions
**Status:** Accepted

The first dashboard is the primary daily workflow for document collection.
Per-row `Fetch` detects whether the row identifier is an ESHIDIS numeric id or
a KIMDIS `PROC` ADAM and fetches documents for that identifier only. Per-row
`ZIP` streams the downloaded local documents for that same row. Batch tools may
remain available for maintenance, but they should not be the main user path.

Long-running commands remain serialized because they write shared runtime
reports and document indexes; the UI must show explicit progress instead of
appearing idle.
