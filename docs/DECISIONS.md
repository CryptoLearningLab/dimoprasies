# Decision Log

## D-113 — Email digest uses existing dashboard evidence only
**Status:** Accepted

Public-works email alerts should become a practical daily digest, but they
must not add work to the initial dashboard load or change notification
semantics. The digest therefore reuses the already assembled dashboard row
payload and the existing per-recipient `notification_log` checks.

Rows already emailed to a recipient remain skipped for that recipient. The new
digest format adds summary counts, reason text and attention buckets only for
the rows that would already be sent.

Budget highlighting is relative to the current digest (`Υψηλότεροι
προϋπολογισμοί`) instead of a hardcoded business threshold. User- or
profile-specific budget thresholds should be introduced later through
configuration/profile settings, not in the email renderer.

## D-112 — Expiring-soon view is derived client-side
**Status:** Accepted

The public-works `Λήγουν σύντομα` view should not slow the initial dashboard
load. It is therefore rendered from the already loaded `dashboard.tenders`
payload in the browser, using existing deadline, source and
`project_operations` fields.

No new endpoint, source scan, file read or per-row backend query should be
introduced for this first version. If future daily metrics need persisted
history or cross-user aggregation, they can be added as a lazy endpoint later.

## D-111 — Project detail timeline is assembled from cached row evidence
**Status:** Accepted

The project detail preview should expose provenance and operational state from
the existing dashboard payload instead of making the operator wait for another
blocking request. Visible rows therefore carry `project_sources`,
`project_operations` and an expanded `project_timeline` derived from already
loaded row data plus one bulk notification-log lookup.

The timeline is not a replacement for immutable raw provenance. It is the
operator-facing summary: sources, ESHIDIS/KIMDIS links, document availability,
email status, AI/admin feedback and cleanup expectations.

## D-110 — Review feedback buttons are user-scoped
**Status:** Accepted

Interactive review feedback represents a user's judgment unless an explicit
global rule/override workflow is used. The false-negative review queue buttons
therefore persist to `user_triage_overrides`, keyed by `(user_email, row_key)`.

`CONFIRM_DROP` removes the row from that user's review queue and keeps it out
of that user's dashboard. `FORCE_KEEP` restores/keeps the row for that user
only. Global `triage_overrides` remain supported for deliberate system-wide
operator rules, but ordinary review clicks must not change another user's
dashboard.

## D-109 — Admin review feedback is persisted before rule changes
**Status:** Accepted

The false-negative review queue should collect explicit operator feedback
before turning individual examples into broader keep/drop rules. A confirmed
correct rejection is stored as `CONFIRM_DROP` and removed from the review
queue, but remains visible in the full hidden audit. A false negative is
stored as `FORCE_KEEP` with the operator reason and reuses the force-keep
override path.

This keeps review work auditable and avoids silently losing either kind of
signal. Future rule or prompt changes should be based on these persisted
feedback examples, not on untracked manual UI decisions.

## D-108 — Visible dashboard rows carry their own explanation
**Status:** Accepted

The public-works dashboard should not require an operator to infer why a row
appears from scattered fields. Every visible row should include a lightweight
`why_visible` explanation and `project_timeline` events derived from already
loaded row data: source, interest match, ESHIDIS linkage, deadline evidence,
document evidence and AI keep reasoning when available.

This explanation belongs in the existing dashboard payload so the preview pane
can render it without a second blocking request. More detailed provenance can
be added later, but the initial operator-facing answer must be cheap and
available for every visible row.

## D-107 — UI rendering is read-only and cache-backed
**Status:** Accepted

Interactive dashboard/admin GET requests should not perform maintenance work
such as deleting expired downloads or rewriting audit-derived state unless
strictly required for the displayed payload. Page rendering should be fast,
read-mostly and cache-backed for a short interval.

Maintenance jobs such as expired file cleanup should run through scheduled or
explicit runtime paths. UI payload caches must be invalidated after discovery,
fetch, AI triage, enrichment, dismiss/restore and similar state-changing
actions.

## D-106 — Production credentials are admin-only local secrets
**Status:** Accepted

Operational credentials such as TEE login details must not be sent through chat
or committed to GitHub. The production UI may provide an admin-only form that
writes approved secret keys to the droplet-local `.env.local` file.

The endpoint must return configured/missing status only and must never return
plaintext secret values. Storing credentials is separate from using them:
automation against a third-party login must still respect CAPTCHA, 2FA,
access-rights and terms-of-use constraints.

## D-105 — Obvious supply/service exclusions do not need false-negative review
**Status:** Accepted

The false-negative review queue is for plausible missed public-works tenders,
not for rows that clearly describe unrelated supplies or services. Rows whose
title clearly indicates fuel/lubricants procurement, student transport
services or telemetry/remote-control system procurement/installation may be
excluded from the review queue and shown in the full audit with a specific
out-of-scope reason.

This rule is intentionally narrow. Generic "προμήθεια", "υπηρεσία" or
"εγκατάσταση" wording is not enough by itself because some contractor-relevant
public works contain mixed procurement/installation language. Road-network
maintenance remains reviewable under D-102.

## D-104 — False-negative review is audit-first
**Status:** Accepted

The public-works admin panel should expose a separate false-negative review
queue for hidden rows that may have been incorrectly excluded. The queue should
prioritize AI drops with public-works signals, missing-deadline candidates and
possible ESHIDIS duplicates.

The queue does not automatically restore or promote rows. It gives the
operator a focused review surface and preserves the existing manual restore
mechanism for rows that need correction.

## D-103 — Source removal needs health evidence
**Status:** Accepted

Public-works sources should not be removed after a single transient failure.
The admin source audit must show recent checks, recent failures, consecutive
failures and last successful check so unstable sources can be classified as
watch, degraded or disable candidates before configuration changes are made.

HTTP 503 from Diavgeia is treated as source health degradation unless it
persists across repeated runs. Existing successful data remains usable while
the source is degraded.

## D-102 — Road-network maintenance is in scope
**Status:** Accepted

Open tenders for maintenance of road, provincial and other road-infrastructure
networks are in scope for the public-works dashboard. They may still require
human review when the documents are ambiguous, but they must not be dropped as
out-of-scope supplies/services merely because maintenance wording is used.

Snow-removal or winter-maintenance packages are also kept for review when the
row has tender/deadline and budget evidence plus road-network infrastructure
wording.

This rule does not override direct assignments, article 118 procedures, signed
contracts or rows whose evidence says they are not open tenders.

## D-101 — Admin audit AI rows use semantic rejection categories
**Status:** Accepted

Rows excluded by AI triage remain visible in the admin audit, but their
category must reflect the AI decision family instead of a generic hidden state.
Administrative/non-tender acts, out-of-scope supplies/services, non-public
works and early signals should therefore be explainable directly from the audit
row with the stored AI reason and confidence.

## D-100 — Admin expired reasons are dashboard-candidate only
**Status:** Accepted

The admin audit explains why rows were removed from the operational dashboard.
Deterministic categories such as `EXPIRED`, `NO_DEADLINE_EVIDENCE` and
`DUPLICATE_CANDIDATE` must therefore apply only to rows that would otherwise
be candidates for the dashboard: interest-matched and not already AI-hidden.

Out-of-scope rows may still appear under `AI_HIDDEN` when AI triage explicitly
removed them, but they must not be labeled as expired merely because they have
a past deadline.

## D-099 — Expired tender cleanup deletes downloads, not provenance
**Status:** Accepted

When a public-works row has a parseable expired deadline, the runtime may
delete local downloaded binary files for that row to control disk usage. It
must keep official source links, ids, metadata, extracted text evidence and
provenance so the document can be re-fetched from ESHIDIS, KIMDIS or the
authority source if needed.

Cleanup is restricted to paths under `work/`. Rows hidden because they lack
deadline evidence are not considered expired and must not trigger file cleanup.

## D-098 — Dashboard expiry is automatic and datetime-aware
**Status:** Accepted

Public-works rows must leave the active dashboard automatically after their
submission deadline has passed. When the row has a time component, visibility
is checked against the full local datetime in the configured locations
timezone. Date-only deadlines remain visible until the end of that date.

The system hides expired rows from the operational dashboard instead of
physically deleting source rows, documents or provenance.

## D-097 — Linked ESHIDIS files are visible in source previews
**Status:** Accepted

KIMDIS and authority previews must not only state that linked ESHIDIS files are
available for ZIP. When linked ESHIDIS attachments exist locally, the preview
payload includes `linked_eshidis_documents` and the browser renders those files
with normal `Open` actions below the link notice.

This keeps the row preview consistent: if the system says official ESHIDIS
files exist, the operator can inspect them directly without first downloading a
ZIP archive.

## D-096 — ESHIDIS downloads are scoped by tender id
**Status:** Accepted

ESHIDIS attachment downloads must be stored under an ESHIDIS-specific directory
inside the configured download root, for example
`work/download_audit/221744/espd-request-v2.xml`.

The UI and database keep using attachment ids and stored `local_path` values,
but new downloads avoid flat-directory filename collisions between projects.
This is required for common filenames such as `espd-request-v2.xml` and for
sha256 integrity checks to remain meaningful.

## D-095 — UI backfill search may skip only after a complete unchanged window
**Status:** Accepted

The public-works UI `Νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ` button uses `/api/discover`.
Bounded searches run source preflight and may skip or selectively refresh only
changed source families.

When `Backfill safety` is enabled, the search is intentionally deeper and may
repeat source discovery until it overlaps the previous successful window.
However, if source preflight is unchanged and the latest successful discovery
run already has a complete watermark, the UI backfill path now returns an
immediate skip instead of repeating expensive ESHIDIS/KIMDIS discovery.

When `/api/discover` returns `skipped=true`, the browser does not start the
follow-up AI triage/enrichment chain. Skipped discovery should end quickly for
the operator instead of occupying the runtime command lock with downstream work
against unchanged rows.

## D-094 — Entalmata scans reuse processed ADA documents
**Status:** Accepted

Diavgeia entalmata decisions are keyed by ADA. When a repeated scan sees the
same ADA with the same document URL and an existing local PDF plus stored
classification/text evidence, the scanner reuses the persisted row instead of
downloading and extracting the PDF again.

The scan still reads current Diavgeia listing pages so new decisions can be
found and old visible rows can be archived out of the configured window, but
unchanged decisions do not repeat document work.

## D-093 — Public-works document analysis is incremental by default
**Status:** Accepted

The public-works `documents analyze` command must not reprocess attachments
that already have usable analysis state. If a document row has an existing
text artifact on disk, or a terminal no-text state such as `UNSUPPORTED_TYPE`,
the command skips it by default and records the skip in the report. Explicit
re-analysis remains available with `--force`.

This keeps manual and scheduled public-works workflows from spending repeated
OCR/extraction time on files that have already been collected and analyzed.

## D-092 — Economic offer is validation-first, not the primary budget source
**Status:** Accepted

Reverse-pricing should not start analytical budget extraction from
`ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΣΦΟΡΑ`. Economic-offer documents remain useful for official
subtotal validation, but they must be penalized in budget routing unless they
visibly contain the complete analytical table with quantities and unit prices.

Standalone `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` files are the strongest budget source. A filename
token such as `ΠΥ` is only weak evidence because it may mean either
`Προϋπολογισμός` or `Πυρασφάλεια`; it needs text/table confirmation before
heavy parsing. Drawings and special studies are skipped before expensive OCR
unless explicit budget evidence is present.

## D-091 — Structured budget rows use the last A/T before unit
**Status:** Accepted

For reverse-pricing budget rows where article/revision tokens appear before the
A/T column, the parser must treat the last three-digit token before the unit as
the A/T number. Earlier three-digit tokens may belong to revision codes such as
`ΗΛΜ 103` or `ΠΡΣ 5321`. The supported layout is:

`description -> article prefix -> revision code -> A/T -> unit -> quantity -> unit price -> amount`.

Examples include `ΝΑΠΡΣ ΠΡΣ 5321 283`, `ΑΤΗΕ ΗΛΜ 34 473` and
`ΗΛΜ Ν\45.1.2 ΗΛΜ 103 348`.

## D-090 — Strict budget filename-only parsing is not a production path
**Status:** Rejected

The experimental strict filename-only pass that parsed only documents whose
path contained `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` is not a production strategy. A live isolated
20-candidate smoke completed only one project and proved that valid budgets
can be split across a named budget PDF plus technical report, financial offer
form or other official attachment. ESHIDIS `221566` is the clearest example:
strict budget-file parsing lost rows and mismatched the subtotal, while the
previous broader deterministic flow reconciled all `36` rows to the official
subtotal.

The project remains on the previous broader reverse-pricing flow with guarded
OCR and validation. Future routing may still prioritize obvious budget files,
but it must not discard other official pricing evidence before validation.

## D-089 — Nested drawing archives must not trigger pricing OCR by parent name
**Status:** Accepted

Reverse-pricing must classify archive children by the child filename before it
allows expensive OCR. A parent archive name such as `ΣΧΕΔΙΑ ΑΡΧ.ΜΕΛΕΤΗΣ` or
`ΣΤΑΤΙΚΗ ΜΕΛΕΤΗ` is not enough to treat every nested PDF as a pricing
candidate. Nested drawings keep provenance/download links and cleanup metadata,
but are skipped before OCR unless the child filename itself contains
budget/pricing evidence such as `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ`, `ΤΙΜΟΛΟΓΙΟ`, `ΠΡΟΜΕΤΡΗΣΗ` or
`ΟΙΚΟΝΟΜΙΚ`, or the archive parent has a strong budget/pricing signal.

## D-088 — Long pricing maintenance commands must expose incremental progress
**Status:** Accepted

Reverse-pricing commands that can spend minutes downloading, routing, OCRing or
reprocessing budgets must emit machine-readable per-project progress when a
progress log is requested. Final JSON reports are still required, but they are
not enough for operational visibility during long runs.

## D-087 — Reverse-pricing completion requires budget total validation
**Status:** Accepted

Reverse-pricing batch runs must not mark a project `COMPLETED` unless the
project has parsed budget rows and the merged project budget passes official
document-total validation. If totals are missing, mismatched or otherwise not
validated, the project remains partial/review even when fetch, OCR and parsing
finished without transport errors.

## D-086 — Reverse-pricing heavy file retention is essential-doc only
**Status:** Accepted

Reverse-pricing may download every ESHIDIS attachment for indexing, OCR and
provenance, but it keeps heavy files locally only for essential operational
documents while the tender is active: invitation, declaration, technical
report/description, budget, pro-measurement and price schedule. Secondary
studies, administrative forms, drawings and archive bundles keep source links,
text artifacts and parsed rows where useful, but not every downloaded binary.

## D-085 — Official standalone budget route guard
**Status:** Accepted

When reverse-pricing AI routing considers both an official standalone ESHIDIS
budget/pro-measurement attachment and a nested archive summary, the standalone
official attachment wins deterministically. AI evidence is still recorded, but
it cannot route parsing away from the higher-provenance official budget file.

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

## D-049 - Non-ESHIDIS source document provenance belongs in SQLite
**Status:** Accepted

Municipal, regional and other non-ESHIDIS source documents are tracked in
SQLite `source_documents`, keyed by source row and document URL. The record
stores provenance, local path, SHA-256, fetch timestamp, source signature and
fetch errors.

Authority document fetchers must reuse unchanged local files when the source
signature and document URL match, rather than downloading duplicate copies on
every enrichment run. Legacy JSON document indexes may remain as UI bridges,
but SQLite is the operational state for skip/fetch decisions.

## D-050 - Scheduled alerts collect documents before presentation
**Status:** Accepted

The normal scheduled path should not require a user to click `Fetch` before the
system can inspect documents, run OCR or send useful alerts. The scheduler runs
automatic document fetch for new, changed or unprocessed non-ESHIDIS candidates
before email alerts when source discovery actually ran.

Manual row `Fetch` remains as retry/admin control. Repeated scheduled runs are
bounded by the candidate-enrichment attempt ledger, ESHIDIS attachment skip
behavior and SQLite `source_documents` provenance, so unchanged rows should not
force repeated downloads.

If source discovery is skipped as unchanged, scheduled auto-fetch is skipped
too. Scheduled auto-fetch also has a small time budget when it does run. If
unresolved rows still need slow external fetches, the scheduled run records
that it stopped by budget and continues to email/audit output instead of
blocking the whole cron run.

Per-target auto-fetch failures are warnings for the scheduled run, not fatal
errors. Discovery, AI triage and email delivery failures can still fail the
scheduled run.

## D-051 - Admin corrections are explicit runtime overrides
**Status:** Accepted

AI triage decisions are reused across runs, so manual corrections are stored
as explicit runtime state instead of silently editing generated reports. The
admin panel writes `FORCE_KEEP` records to SQLite `triage_overrides` when a
user restores an AI-hidden row and records the user's reason as feedback.

Rows hidden by `Δεν με ενδιαφέρει` are restored by removing their dismissal
state from SQLite `tender_dismissals` and the legacy ignored-tenders JSON
bridge. Duplicate and expired rows remain audit-only in the first admin gate.

Admin access is inside the main UI as an `Admin panel` tab. Login supports
email one-time codes to the configured admin/alert email, with optional
password fallback through runtime environment variables.

## D-052 - OCR is an optional bounded fallback
**Status:** Accepted

OCR is used only as fallback for weak PDF text extraction, not as the default
path for every document. A PDF needs OCR when embedded extraction fails,
returns no text, lacks a text extractor, or returns very short text.

The runtime uses available system tools (`pdftoppm` and `tesseract`) and records
`OCR_TOOL_MISSING`, `OCR_FAILED`, `OCR_NO_TEXT_FOUND` or
`OCR_TEXT_EXTRACTED` in document analysis provenance. Missing OCR tooling is
non-fatal. The first OCR gate is bounded to the first 3 pages so cron runs do
not become unbounded full-document OCR jobs.

## D-053 - Admin/user passwords are invite-set and hashed
**Status:** Accepted

Tender Radar can create local UI users in SQLite, but it must not store
plaintext passwords. Passwords are set only through email setup/invitation
links. The invite token is stored as a SHA-256 hash, expires after a short
operator window and is marked used after a successful password set; the
password is stored as PBKDF2-SHA256 with a random salt.

The configured owner email becomes `admin`. Admins may invite additional
`user` or `admin` accounts from the Admin panel. `user` accounts do not gain
admin audit/restore/invite permissions. The previous email one-time code login
and runtime env password remain as owner/emergency fallback paths.

## D-054 - The daily UI is private by default
**Status:** Accepted

Tender Radar's dashboard and action APIs require an authenticated local UI
session. The public HTML shell may be served so users can log in, but
dashboard data, source polling details, document previews, fetch/zip actions,
dismissals and reports are not available without a session.

SQLite users created through invite/password setup may access the main app.
Only role `admin` may access audit, restore and user invitation controls.

## D-055 - AI triage consumes bounded document evidence, not raw archives
**Status:** Accepted

Fetched/OCR documents are summarized into bounded evidence snippets before
OpenAI triage. The AI payload includes provenance fields such as document name,
document type, extraction status, OCR status/error, fetch error, deterministic
ESHIDIS ids and selected snippets around high-value contexts like article 2.2,
ESHIDIS wording, official eprocurement URLs and economic-offer forms.

The system does not send unbounded raw PDFs or whole archive contents to the
model. Deterministic ESHIDIS ids found in document text are merged into the row
before AI classification, and later enrichment uses those ids to fetch the
official ESHIDIS folder directly instead of reprocessing the original
municipal/authority/KIMDIS source.

Cached AI triage rows are reused only when their `triage_signature` still
matches the current dashboard metadata and bounded document evidence. If a row
gets new fetched/OCR text or changed identifiers, it becomes pending for one
fresh AI pass; unchanged rows keep skipping OpenAI.

## D-056 - Prompt changes invalidate AI triage cache
**Status:** Accepted

The AI triage cache signature includes an explicit `AI_TRIAGE_PROMPT_VERSION`.
When the classifier prompt is tightened from observed production failures, the
affected rows are rechecked once instead of silently reusing stale decisions.

The classifier prompt is strict about common false keeps observed in production:
technical-consultant services, standalone studies, direct assignments, supplies
even when they include installation or commissioning, vehicle/machinery repairs,
transport services, Μη.Μ.Ε.Δ. drawings, awards, contracts and administrative
approvals are excluded unless the row is clearly an active open public-works
tender with a future submission deadline.

If the normalized AI decision is a drop decision, any model-returned
`eshidis_id_candidates` are discarded. Downstream ESHIDIS verification is fed
only by rows still kept for daily review.

## D-057 - Cross-source ESHIDIS links must be verified before dedup
**Status:** Accepted

KIMDIS, municipal, regional and other authority rows may expose candidate
ESHIDIS ids through fetched/OCR documents or AI triage, but those hints do not
hide or replace source rows by themselves.

A cross-source relation becomes dedup evidence only after an official ESHIDIS
fetch succeeds through `pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{id}`.
Verified relations are stored in SQLite `verified_tender_links` with source
row key, source identifier, target ESHIDIS id, source signature, verification
time and evidence JSON.

The dashboard prefers the official ESHIDIS row only when such a persisted
verified link exists and the official ESHIDIS row is present. Non-ESHIDIS rows
without verified links remain visible as review candidates with
`NO_VERIFIED_ESHIDIS_LINK`; title-only deduplication remains forbidden.

An exception is allowed for strong explicit linked-id duplicates: when a
non-ESHIDIS row contains an explicit linked ESHIDIS id that already exists as
an official ESHIDIS row, and at least two independent fields match the official
row (title, deadline, budget or authority), the dashboard may hide the
non-ESHIDIS row as `STRONG_LINKED_ESHIDIS_DUPLICATE`. This still forbids
title-only deduplication and does not persist a verified link unless the
official fetch verification gate has run.

When a non-ESHIDIS row has no direct submission deadline but links to an
official ESHIDIS row that has a known deadline, the dashboard uses the linked
official ESHIDIS deadline for active/expired filtering. Missing authority
deadline text must not keep an already-expired linked ESHIDIS project visible
on the daily dashboard.

## D-058 - KIMDIS connected acts use the public Open Data API
**Status:** Accepted

Για forced σύνδεση ΚΗΜΔΗΣ `26PROC...` με πιθανό Α/Α ΕΣΗΔΗΣ χρησιμοποιούμε
το δημόσιο read-only endpoint
`https://cerpp.eprocurement.gov.gr/khmdhs-opendata/adamChain/{referenceNumber}`
και τα αντίστοιχα public attachment endpoints. Δεν κάνουμε scraping της
JSF φόρμας `upgkimdis/unprotected/home.xhtml` όταν υπάρχει σταθερό Open Data
API. Τα ευρήματα αποθηκεύονται ως candidate evidence και γίνονται verified
μόνο αφού περάσει official fetch από `pwgopendata`.

## D-059 - Daily dashboard requires verified future deadline evidence
**Status:** Accepted

The main daily dashboard is an actionable bidding list, not a raw discovery
queue. A row is visible only when the system has a parseable submission
deadline that is still active after the current date. The deadline may come
from the official ESHIDIS row, from a directly discovered source field, from a
linked official ESHIDIS row, or from fetched document evidence such as a
declaration, summary declaration, extension notice or economic-offer form.

Rows without a verified/parseable future deadline are hidden from the main
dashboard and remain available through audit/review paths. This avoids showing
expired authority rows or candidates whose publication date was mistaken for a
submission deadline. The parser must keep provenance for document-derived
deadlines, including document name, URL/source URL, matched text and snippet.

## D-060 - Admin user id display uses SQLite rowid
**Status:** Accepted

The admin panel displays each user with the existing SQLite `rowid` from the
`admin_users` table. We do not add a parallel UUID/user-id column until there
is a concrete cross-system identity requirement. This keeps the current login
database simple while giving the admin screen a stable local identifier for
support and audit discussions.

## D-061 - User roles are bounded to admin, tester and user
**Status:** Accepted

Tender Radar account roles are intentionally bounded to `admin`, `tester` and
`user`. `admin` can access the admin panel and manage invitations/roles.
`tester` and `user` can authenticate to the main app but do not receive admin
panel permissions. The admin role update flow accepts email or displayed
SQLite user id, and protects the system from removing the final enabled admin
or demoting the currently active admin session.

## D-062 - Nationwide search is disabled until it has a safe separate design
**Status:** Accepted

The daily Tender Radar product is a local-interest workflow. The former
All-Greece UI scope is disabled because it shared discovery reports, source
fingerprints, dashboard state and enrichment paths with the local workflow.
That could cause excessive KIMDIS/authority candidates, expensive document
fetch/OCR/AI work, and confusing state after switching back to the local scope.

Until a separate nationwide design is approved, user-facing dashboard,
AI triage, enrichment, scheduled alert and CLI scope paths are restricted to
`focus`. New search profile templates default to `nationwide: false`.

Future nationwide support must be implemented as a separate product gate with
mode-aware state, ESHIDIS-only discovery by default, no automatic non-ESHIDIS
fetch/OCR/AI, explicit resource limits, and separate audit/reporting so it
cannot pollute or slow the local daily workflow.

## D-063 - Diavgeia entalmata are a separate SQLite workflow
**Status:** Accepted

The Diavgeia payment-warrant/decision utility is integrated as a backend
workflow, not by embedding the Windows `.exe`. Configuration lives in
`config/diavgeia_entalmata.yml`; state lives in SQLite table
`diavgeia_entalmata`; downloaded evidence lives under
`work/download_audit/diavgeia_entalmata`.

The user-facing `Αρχεία` tab is replaced by `Εντάλματα`. It shows only
keyword-matched decisions from the configured recent window, currently 15 days.
Older visible decisions are archived to an `old` folder and marked
`ARCHIVED`; rejected non-matches remain as retained audit evidence, not as
front-page items. This workflow is independent of public-works tender discovery
and must not affect tender dashboard filtering, ESHIDIS/KIMDIS deduplication or
daily email alerts until a separate product gate is approved.

## D-064 - Deep entalmata scans are explicit CLI runs
**Status:** Accepted

The daily `Εντάλματα` UI scan keeps the configured bounded page depth from
`config/diavgeia_entalmata.yml`. Deeper Diavgeia checks, such as a 100-page
archive/backfill smoke, must be explicit operator runs through
`tender-radar entalmata scan --max-pages N`.

This prevents an ordinary UI click from downloading and parsing excessive PDF
history, while still allowing controlled evidence checks with the same
filters, SQLite state and archive behavior.

## D-065 - Reverse content search starts as a read-only active-row query
**Status:** Accepted

The `Αντίστροφη αναζήτηση` tab starts as a fast read-only search over the
currently visible active tender dashboard rows and already extracted/evidenced
document text. A query must not trigger source discovery, full-depth scanning,
document fetch, OCR or AI classification.

This gives the UI a stable Mode B contract before adding richer search grammar,
SQLite FTS indexing, document filters, article/revision parsing, quantities or
price extraction. Future expansion can replace the backend query engine without
changing the basic UI request/response shape.

## D-066 - Front-page tender dismissals are user-specific
**Status:** Accepted

The `Δεν με ενδιαφέρει` action is personal state. A user hiding a tender must
not remove it from another user's dashboard. New dismissals are stored in
SQLite table `user_tender_dismissals` keyed by `user_email` and `row_key`.
Legacy global dismissals remain readable for audit/backward compatibility, but
new UI actions do not write global ignore state.

Admin restore removes both legacy and per-user dismissals for the row, then
adds the existing force-keep override. Admin audit lists dismissed rows with
the user email so support can distinguish personal preference from AI/system
filtering.

## D-067 - Password reset reuses secure setup links
**Status:** Accepted

Password reset uses the same invite/setup-token flow as first password
creation. The app sends a time-limited `/password-setup?token=...` link to an
existing enabled user and stores only the resulting password hash.

The reset request returns a generic success response for unknown emails to
avoid exposing whether an address is registered.

## D-068 - Scheduled entalmata run with public works cron
**Status:** Accepted

The six-hour runtime scheduler is the single production automation entrypoint
for daily operator checks. It now runs the bounded Diavgeia entalmata scan in
the same scheduled execution as public-works polling, AI triage, document
collection and email alerts.

Entalmata failures are warning-only for the combined scheduled run. They must
be visible in JSON/Markdown audit reports, but they must not block public-works
alerts. Deeper entalmata backfills remain explicit CLI runs.

Email alerts support multiple runtime recipients from `ALERT_EMAIL_TO`,
`EMAIL_ALERT_TO` or `EMAIL_TO`. Notification de-duplication remains scoped per
recipient, so adding a mailbox does not suppress rows that were only sent to
another mailbox.

## D-069 - Entalmata alerts are independent one-time notifications
**Status:** Accepted

Diavgeia entalmata alerts use the same email delivery path as public-works
alerts, but their notification state is stored under a separate
`entalmata_email` channel keyed by `ENTALMA:{ADA}` and recipient.

This keeps one-time delivery semantics for each mailbox without mixing payment
warrants with tender rows. Public-works rows remain de-duplicated under the
existing `email` channel.

## D-070 - Password setup links use a short one-time window
**Status:** Accepted

Password setup and reset links now expire after 60 minutes. A link is marked
used only after a successful password set, not merely when the page is opened,
so mobile refreshes or accidental previews do not burn the token before the
user completes the form.

## D-071 - Reverse pricing is isolated from local tender monitoring
**Status:** Accepted

The reverse-pricing / article-intelligence feature is a separate module with
its own SQLite tables, role gate and future automation path. It must not reuse
or mutate the local public-works dashboard state except for shared auth and
explicit read-only compatibility where needed.

The first source of truth for this module is nationwide active ESHIDIS public
works. KIMDIS and authority pages may later be used as auxiliary discovery
signals, but only after the ESHIDIS-only path passes smoke tests.

Heavy fetched documents for reverse pricing are temporary extraction inputs.
After text and structured budget rows are persisted, PDF/ZIP payloads should
be deleted the same day unless an explicit operator/debug run asks to retain
them.

The six-hour cron must not run the new reverse-pricing workflow until the
manual controlled fetcher, budget parser, cleanup and UI smoke gates are all
passing.

## D-072 - Reverse pricing keeps raw rows and serves merged rows
**Status:** Accepted

Reverse-pricing extraction stores structured budget rows per source document
for audit and provenance. Search and user-facing analysis should prefer a
merged per-project budget source when it exists.

The merge groups rows by `row_number` and chooses the strongest available row
using source priority and extraction confidence. Official budget documents are
preferred over technical reports for overlapping rows, while technical reports
may fill row ranges missing from the budget PDF text layer. This preserves
traceability without showing duplicate article hits to users.

## D-073 - Reverse pricing indexes only pricing-candidate documents by default
**Status:** Accepted

`pricing ingest-eshidis` stores every official ESHIDIS attachment as document
provenance, but it only extracts/OCRs files whose names indicate a likely
pricing source such as budget, price list, technical report or financial offer.

Non-pricing files are marked `SKIPPED_NON_PRICING_DOCUMENT` and are treated as
already processed on repeated runs. Operators can still use `--force` for a
debug reprocess, but normal runs must not spend time OCRing drawings,
decisions, declarations or unrelated PDFs before the pricing gate proves a need
for them.

## D-074 - Reverse pricing treats study bundles and AT columns as budget sources
**Status:** Accepted

Some ESHIDIS projects publish the actual budget table inside a bundled study
PDF whose filename is `ΜΕΛΕΤΗ...pdf`, not a standalone `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` file.
Such documents are pricing candidates when fetched by the reverse-pricing
module.

For Greek budget layouts with a separate `Α.Τ.` or `Αρ. Τιμ.` column, that
column is the stable project row identifier. The leftmost local row number may
restart inside every category and must not be used as the final merged budget
row number.

## D-075 - Reverse pricing recovers partial indexed state before network
**Status:** Accepted

If `pricing ingest-eshidis` finds persisted raw pricing rows for a project but
no merged project budget, it first performs a cheap local consolidation and
returns `PARTIAL_PROJECT_RECOVERED_WITHOUT_REFETCH`.

This prevents interrupted or timed-out runs from forcing a new browser,
download or OCR cycle when enough structured rows already exist to rebuild the
merged budget. Operators can still pass `--force` when they deliberately want a
full official refetch and re-index.

## D-076 - Reverse pricing validates row arithmetic before trusting a merge
**Status:** Accepted

Merged reverse-pricing budget rows include arithmetic validation:
`quantity * unit_price ~= amount`, with tolerance for small displayed-unit-price
rounding differences.

When multiple candidates share the same project row number, amount-valid rows
are preferred over rows whose extracted numeric columns do not reconcile. This
keeps the official source text as provenance while using arithmetic consistency
as an additional guard against layout/table carry-over parsing errors.

## D-077 - Reverse-pricing completion is run-accounted
**Status:** Accepted

The reverse-pricing ESHIDIS ingest is considered complete only when the batch
run has recorded an explicit outcome for every active ESHIDIS candidate it
selected from discovery.

Manual smoke limits are allowed, but any explicit `project_limit`, partial
project, failed project or invalid identifier marks the run `INCOMPLETE`. A
small successful subset must not be presented as full active-list completion.

`max_new_projects` is a different production control: it means "process up to
N new or incomplete projects after skipping already complete candidates" and
can finish successfully when that target is reached inside the discovered
active window.

## D-078 - Reverse-pricing active ESHIDIS discovery uses official grid export
**Status:** Accepted

The ESHIDIS active-search Oracle ADF table declares the full active row count
but only renders a small virtualized window in the browser DOM. Reverse-pricing
active discovery therefore uses the public `Εξαγωγή σε Excel` action as its
primary extraction path.

The exported `.xls` is an HTML table containing the full filtered active list.
The browser DOM and captured ADF response parsing remain fallback diagnostics,
but they must not be the production limit for nationwide reverse-pricing
discovery.

## D-079 - UI sessions persist in SQLite
**Status:** Accepted

Authenticated UI sessions are stored by hashed token in SQLite with the same
expiry as the browser cookie. The in-memory session map is only a cache.

This lets a user reload the page, or survive a service restart/deploy, without
losing access or the ability to load the latest run status. Logout deletes the
persistent session and clears the browser cookie.

## D-080 - Reverse pricing requires document-level budget sum validation
**Status:** Accepted

Merged reverse-pricing budgets are not considered fully audited only because
row extraction succeeded. After consolidation, the module must compare the
database sum of merged row amounts against an official subtotal extracted from
the source budget/study document when such a subtotal is available.

The validation result is explicit:

- `OK`: database sum matches the official source subtotal within tolerance.
- `MISMATCH`: extraction succeeded but the database sum does not reconcile.
- `NO_REFERENCE_TOTAL_FOUND`: rows were extracted, but no comparable official
  subtotal was found in the extracted text.

This keeps later runs skip/read-only friendly: once a project has extracted
rows plus an `OK` document-total validation, future runs can trust that audit
state from `pricing_projects.metadata_json` unless the source changes or a
force reprocess is requested.

## D-081 - Reverse-pricing skip requires full OK budget audit
**Status:** Accepted

Reverse-pricing active batch runs must not skip a project merely because
downloaded documents and merged budget rows already exist. A project is
`SKIPPED_ALREADY_COMPLETE` only when the persisted `pricing_budget_audit` has:

- `amount_validation.ok = true`
- `document_total_validation.ok = true`

Projects with `MISMATCH`, `NO_REFERENCE_TOTAL_FOUND`, row arithmetic failures
or no audit remain eligible for the next bounded pricing run. This prevents
bad or partial extractions from being frozen into the database as if they were
verified.

## D-082 - Reverse-pricing audits prefer review over false OK
**Status:** Accepted

Reverse-pricing budget audits must not mark a project complete by matching an
irrelevant or ambiguous total. Quantity/area totals, trailing `Π2: 0,00`
columns and totals from weaker non-budget documents must be guarded against
even when this keeps the project in `NEEDS_REVIEW`.

The accepted behavior is to leave a project incomplete until the merged
database rows reconcile with an official monetary subtotal from the source
documents. A lower `OK` count is preferable to a false completed audit that
would later pollute the deep-analysis database.

## D-083 - AI budget routing is advisory and validation-guarded
**Status:** Accepted

Reverse-pricing may use AI to choose the most likely budget document and page
range before deterministic parsing, especially when the budget is embedded in
a study, declaration or archive.

AI routing does not write budget rows and does not mark a project complete.
The selected route is persisted only as provenance/audit metadata. If parsing
only the routed document fails row arithmetic or official subtotal validation,
the command must fall back to full deterministic reprocess for that project.

This lets AI reduce search space and identify hard document layouts without
allowing a bad route to degrade the pricing database.

## D-084 - Official standalone ESHIDIS budget attachments outrank archive summaries
**Status:** Accepted

In reverse-pricing, a standalone official ESHIDIS attachment whose name
contains `ΠΡΟΜΕΤΡΗΣΗ`, `ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ` or both is stronger routing evidence
than a nested PDF inside a ZIP/study bundle that contains a `ΣΥΝΟΠΤΙΚΟΣ
ΠΡΟΫΠΟΛΟΓΙΣΜΟΣ` table.

The UI may still run pricing ingestion with heavy-file cleanup enabled, but
official standalone budget/pro-measurement attachments must be preserved until
extraction and validation have had a chance to use the original PDF. If a
non-preserved file is deleted after text extraction, SQLite must clear
`pricing_documents.local_path` and record `heavy_file_deleted_at`; stale paths
must not make the system believe a deleted PDF is available.

ZIP extraction must repair common legacy Greek filename encodings before
indexing child documents, so router prompts and provenance do not receive
mojibake paths as primary document evidence.

## D-085 - Lump-sum budgets are valid single-row pricing budgets
**Status:** Accepted

Reverse-pricing must support public-works budgets that are explicitly
structured as `κατ' αποκοπή` instead of analytic article rows.

When an official budget document contains a trusted works subtotal such as
`Συνολική Δαπάνη Εργασιών` and the surrounding text states that the works are
priced with a lump-sum amount, the parser may persist one budget row with:

- the detected table/article reference, such as `Πιν. Α`;
- unit `κ.α.`;
- empty quantity and unit price;
- amount equal to the official works subtotal.

This is preferred over parsing unrelated nested study schedules from ZIP
attachments that contain broad words such as `ΜΕΛΕΤΗ` but are not themselves
pricing documents.

## D-086 - Reverse-pricing keeps only essential heavy files by default
**Status:** Accepted

Reverse-pricing must not keep every downloaded PDF/ZIP locally after text
extraction. Heavy local retention is reserved for operationally important
source files until the tender deadline:

- invitation / `ΠΡΟΣΚΛΗΣΗ`;
- declaration / `ΔΙΑΚΗΡΥΞΗ`;
- technical report / description;
- standalone budget files;
- embedded files whose extracted text proves they contain the analytical
  budget section.

Secondary files such as drawings, ΣΑΥ/ΦΑΥ, static/electromechanical/
environmental/geological studies, broad archives, economic-offer templates,
pro-measurements and price schedules are not retained by filename alone.
They remain represented by extracted text, source URLs, archive-child names
and provenance.

Cleanup/refetch must be audited before mutation. The accepted workflow is
`pricing storage-audit`, then dry-run `pricing storage-repair`, then
backup-and-apply only when the report shows the exact affected projects and
attachments.
