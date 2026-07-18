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

## D-026 - Bounded discovery is not a no-miss guarantee
**Status:** Accepted

Higher row/page limits reduce miss risk, but they do not prove complete
coverage after a multi-day gap. A no-miss discovery workflow needs persisted
run metadata and backfill logic that scans each source until it reaches the
last successful discovery window or a documented source exhaustion condition.

The UI may expose bounded scans for speed, but reports must make partial
source failures visible and must not imply formal completeness from a fixed
limit alone.

## D-027 - UI long-running actions use background jobs
**Status:** Accepted

Long-running UI actions must not keep the initiating HTTP request open while
CLI/source work runs. The UI server returns a short-lived in-memory `job_id`
with HTTP `202`, runs the work in a background thread, and exposes job status
through `/api/jobs/{job_id}` for browser polling.

The current implementation is process-local and suitable for local/tunnel
preview. A future multi-process production deployment should persist job state
or use an external queue.

## D-028 - KIMDIS cross-references can trigger ESHIDIS folder fetch
**Status:** Accepted

When a KIMDIS or municipal-source document explicitly contains an ESHIDIS
numeric id, the system may use that id as an official cross-reference to fetch
the fuller ESHIDIS detail and attachment folder.

This creates provenance-linked records only. It does not merge KIMDIS and
ESHIDIS records by title, and it does not promote any candidate to
`VERIFIED_ACTIVE` without the separate status-verification gate.

## D-029 - Discovery completeness is measured with runtime watermarks
**Status:** Accepted

Discovery runs persist runtime metadata under `work/derived/` with source
family, depth, candidate ids, source errors and watermark status. A run is
considered complete only when it has no source/command failures and it either
reaches candidate ids from the previous successful run window or documents
source exhaustion.

Bounded demo scans remain available for speed, but they are labeled as
bounded and do not imply no-miss coverage after a long gap.

## D-030 - Authority website adapters are discovery-only
**Status:** Accepted

Municipal and regional website adapters feed candidate records into the
expanded discovery/dashboard path with source URL, detail URL, attachments,
retrieved-at time and parser status.

These records are not active-status proof. When they expose an official
KIMDIS `PROC` ADAM or ESHIDIS numeric id, the UI may use that explicit
cross-reference for the existing official fetch path. Otherwise they remain
`AUTHORITY_DISCOVERY_CANDIDATE` rows for human review.

## D-031 - Municipal attachments use a separate runtime document index
**Status:** Accepted

Documents downloaded directly from municipal/authority pages are stored under
`work/download_audit/authority/` and indexed in
`work/derived/authority_documents.json`.

They are available for preview and ZIP from the UI, but they are not imported
as ESHIDIS attachments unless an explicit official ESHIDIS id is fetched
through the existing official adapter.

Dismissed dashboard rows are stored in `work/derived/ignored_tenders.json` and
filtered out of subsequent dashboard payloads by row key.

## D-032 - AI triage is advisory before dashboard enforcement
**Status:** Accepted

OpenAI-backed classification may be used to rank discovery rows as active
tender, tender candidate, early signal, administrative, out-of-scope
supply/service, or not public works.

The AI result is advisory until reviewed or backed by deterministic rules. It
must not delete provenance, deduplicate by title, or promote rows to
`VERIFIED_ACTIVE`. Production UI use should read cached triage results or run
as a background job with polling, not make blocking model calls during normal
dashboard rendering.

## D-033 - Daily discovery starts with source fingerprint preflight
**Status:** Accepted

The UI daily discovery action runs a cheap source fingerprint preflight before
starting expensive ESHIDIS/KIMDIS/authority discovery commands. If the latest
source tokens match the saved baseline, the UI returns cached dashboard data
with `SKIPPED_UNCHANGED` and runs no expensive steps.

Temporary preflight failures stay visible as warnings. When the overlapping
successful source tokens are unchanged, the UI may return
`SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS` instead of forcing a full scan that
would likely be slow or fail on the same unavailable source.

Only clean fingerprints replace the complete baseline after a successful full
discovery run. This preserves provenance and does not claim no-miss coverage
for sources that were unavailable during preflight.

## D-034 - Non-ESHIDIS changed sources refresh selectively
**Status:** Accepted

When source preflight identifies specific changed KIMDIS or
municipal/regional/Diavgeia/TED source ids, the UI may run a selective
expanded-report refresh for those source ids only. Unchanged sources are kept
from the previous expanded report and reported as `SKIPPED_UNCHANGED`.

If the changed source cannot be identified, the system falls back to full
discovery rather than producing an unsafe partial refresh. The ESHIDIS active
browser search remains a special heavy source; selective non-ESHIDIS refreshes
reuse the existing ESHIDIS candidate report unless the user runs full/backfill
discovery.

## D-035 - ESHIDIS rows are canonical dashboard representatives
**Status:** Accepted

When a KIMDIS or municipal/regional source row explicitly links to an ESHIDIS
id that is already present as an active/canonical ESHIDIS dashboard row, the
dashboard hides the secondary row and keeps the ESHIDIS row.

This is deterministic duplicate suppression, not title-only deduplication and
not AI deletion. The suppressed source row remains in raw reports/provenance.
SQLite-only stale ESHIDIS metadata without a deadline does not suppress a
KIMDIS row, because it may be the only actionable document row.

## D-036 - ESHIDIS id extraction is context-first
**Status:** Accepted

The current ESHIDIS id extractor treats 6-digit ids as the primary modern
pattern and no longer uses broad 7-digit matching. Five-digit ids are accepted
only as a narrow legacy fallback when the nearby text explicitly says ESHIDIS.

Accepted high-confidence contexts include official `resources/search/<id>`
URLs, declaration article `2.2` references to ESHIDIS/eprocurement, guarded
`Α/Α Διαγωνισμού <id>` text near ESHIDIS/publicworks wording, and
`ΕΝΤΥΠΟ ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ` documents containing `Α/Α ΣΥΣΤΗΜΑΤΟΣ:
<6 digits>`.

Plain numeric strings or plain `Α/Α Συστήματος` without those contexts are not
treated as ESHIDIS ids.

## D-037 - UI discovery uses delta-capable source refresh before full discovery
**Status:** Accepted

The daily UI search should not run full discovery when source fingerprint
preflight identifies only changed sources that have a known selective refresh
path. `eshidis_active_search`, KIMDIS families and configured authority
adapters are treated as delta-capable. The changed source is refreshed and the
expanded report is merged with the previous report for sources marked
unchanged.

Full discovery remains the fallback only when there is no previous baseline,
changed source ids cannot be identified, backfill is explicitly requested, or
the changed source is outside the delta-capable set.

## D-038 - Public-works filtering starts with deterministic gate
**Status:** Accepted

Daily discovery rows must pass a deterministic public-works gate before they
enter the default dashboard lists. ESHIDIS active-search rows are kept as
official public-works source rows. KIMDIS and authority rows are kept only when
metadata shows public-works terms plus tender/procurement/document evidence, or
when a public-works signal is strong enough for manual review.

Clear administrative/news/personnel/election/meeting rows and out-of-scope
supply/service rows are filtered from daily focus lists but retained in raw
reports with a `public_works_gate` decision and reason. AI triage remains a
second advisory layer, not the only filter.

## D-039 - Official tender status belongs only to ESHIDIS rows
**Status:** Accepted

Dashboard rows may come from ESHIDIS, KIMDIS, municipal or regional sources,
but only ESHIDIS rows are labeled as official tender rows. KIMDIS and authority
rows remain candidates unless an explicit ESHIDIS id is extracted from their
documents or source metadata.

When a non-ESHIDIS row yields an ESHIDIS id, the system uses that id to fetch
the official ESHIDIS detail and attachment folder. This creates a linked
official path but does not merge records by title and does not promote
anything to `VERIFIED_ACTIVE` without the separate status-verification gate.

## D-040 - Linked ESHIDIS enrichment is attempted once per unresolved id
**Status:** Accepted

After discovery finds explicit linked ESHIDIS ids in KIMDIS or authority rows,
the UI attempts the official ESHIDIS detail and attachment fetch for ids that
are not already canonical.

If an id still does not become canonical after the attempt, it is recorded in
`work/derived/linked_eshidis_fetch_attempts.json` and skipped on later bounded
searches. This prevents repeated slow retries while preserving the candidate
row and failure evidence for manual review or a later explicit Fetch action.

## D-041 - Runtime state is canonical in SQLite
**Status:** Accepted

Daily operational state belongs in SQLite, not only in mutable JSON files under
`work/derived/`.

Source fingerprints, source run audit rows, permanent tender dismissals and
notification-send records are persisted in `data/tender_radar.sqlite`.
Existing `work/derived` JSON files may remain as legacy/runtime artifacts while
specific flows are migrated, but new poller/email/ignore behavior should use
the SQLite helpers first.

## D-042 - Source preflight decisions are per-source
**Status:** Accepted

Source polling compares each discovery-relevant source independently. A source
timeout or changed fingerprint is recorded against that specific source in
SQLite and should not trigger global full-depth discovery unless the changed
source has no selective refresh path or there is no usable baseline.

The legacy aggregate fingerprint JSON may still be written for compatibility,
but the operational model is per-source state and per-source run audit.

## D-043 - Email alerts consume dashboard state only
**Status:** Accepted

Email notification is a reporting action, not a discovery action. It consumes
the already refreshed dashboard rows and must not run full-depth discovery,
source polling, document fetching or AI classification as part of sending.

Duplicate prevention is keyed by `row_key`, channel and recipient in SQLite
`notification_log`. A row is recorded as sent only after a real send succeeds;
dry-runs do not mutate notification state.

## D-044 - Scheduled runs are bounded and audited
**Status:** Accepted

The droplet scheduler uses `tender-radar runtime scheduled-run` as the single
automation entry point. It runs bounded daily discovery with `backfill=False`,
then incremental AI triage, linked-candidate enrichment and email alerts.

Each scheduled run writes JSON and Markdown audit artifacts containing source
polling counts, changed sources, skipped sources, source errors and email
new/skipped/sent counts. Existing row-key AI decisions are reused, so the
scheduled job sends only untriaged current dashboard rows to OpenAI.
Full-depth/backfill discovery remains an explicit manual action, not the
default 6-hour schedule.

## D-045 - ESHIDIS scheduled preflight uses candidate snapshots
**Status:** Accepted

The `eshidis_active_search` browser page is not a stable cheap fingerprint
source because session ids, page markup and timeouts can change without a new
tender. Scheduled source preflight therefore uses the latest
`eshidis_active_candidates.json` candidate snapshot as the cheap fingerprint
when available.

This makes the 6-hour scheduler skip ESHIDIS discovery unless a new candidate
snapshot has actually been produced by an explicit or successful discovery run.
It is a pragmatic runtime optimization; full/backfill discovery remains
available as an explicit manual operation.

## D-046 - Transient source errors preserve last good fingerprints
**Status:** Accepted

A temporary source timeout or HTTP 503 is not evidence of new tender content.
When a source fails during preflight, SQLite keeps the previous successful
fingerprint and metadata token/date while recording the latest status and error
message.

This prevents error/recovery cycles from creating false changed-source triggers
and avoids unnecessary scheduled discovery runs.

## D-047 - Production email alerts use runtime SMTP env
**Status:** Accepted

Production email delivery is configured through droplet runtime environment
keys, not through repository files or chat-visible code. The scheduler may be
enabled only after a real SMTP send succeeds and `notification_log` records the
sent rows after success.

The current production timer runs every 6 hours through systemd and relies on
SQLite `notification_log` to prevent duplicate alert sends to the same
recipient.

## D-048 - Droplet UI is exposed through HTTPS reverse proxy
**Status:** Accepted

The Tender Radar UI should not be accessed through a raw public application
port. The droplet uses Caddy as a reverse proxy on ports 80/443, with automatic
HTTPS certificates and HTTP-to-HTTPS redirects.

The Python UI process listens on `127.0.0.1:8765` only. Public browser access
goes through the HTTPS hostname, currently `165.227.143.152.sslip.io` until a
user-owned domain or subdomain is configured.
