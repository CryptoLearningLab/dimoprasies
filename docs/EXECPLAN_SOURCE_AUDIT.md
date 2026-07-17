# ExecPlan — PHASE 1 Source Audit

## Purpose

Establish the first repeatable, public-source proof for Greek public works tender
retrieval without claiming crawler completeness or verified active status.

## Current State

PHASE 0 is complete. The repository has an installable Python package, CLI,
configuration validation, structured logging, schema draft and tests. Source
commands are placeholders until source behavior is audited.

## Scope

- Inspect the public ESHIDIS works search entry point.
- Compare direct HTTP behavior with browser-required behavior.
- Prove extraction of a real tender reference and attachment link from a public
  authority page.
- Add a minimal source health check and adapter tests.
- Record TLS/session/browser blockers and captured browser form behavior.

Out of scope: full pagination, production ESHIDIS browser automation, document
download, parsing, active-status verification and Excel export.

## Milestones

1. Re-run PHASE 0 gate.
   - `python -m pytest`
   - `tender-radar config validate`
2. Inspect ESHIDIS active works URL.
   - Direct HTTP should be classified as reachable or blocked with evidence.
   - JavaScript/Oracle ADF behavior must be recorded.
3. Add minimal source adapter proof.
   - `tender_radar.sources.eshidis.health_check`
   - authority page tender-reference extraction
   - tests for both parsing paths
4. Record `docs/SOURCE_AUDIT.md`.
5. Update progress and next task.
6. Capture browser POST shape with Playwright.

## Data and Interfaces

Primary ESHIDIS public works search:
`https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/active_search_main.jspx`

Public authority sample:
Megαλόπολη tender page for Α/Α ΕΣΗΔΗΣ `219879`, used only as a public
retrieval proof and not as a status source of truth.

CLI:

```powershell
tender-radar sources health
tender-radar sources health --allow-insecure-tls
```

## Validation

- Unit tests for ESHIDIS loopback detection.
- Unit tests for authority page extraction.
- Live source health check evidence recorded in `docs/SOURCE_AUDIT.md`.

## Progress

- PHASE 0 gate re-run and passed.
- Source helper module added under `src/tender_radar/sources/`.
- CLI command `sources health` added.
- Tests increased from 3 to 5 and pass.
- Live HTTP evidence collected.
- Browser inspection collected stable field/button ids and ADF POST shape.
- Known-id probes did not return visible rows for tested status combinations.

## Decisions

- Keep default TLS verification strict.
- Permit `--allow-insecure-tls` only for source-audit diagnosis.
- Treat ESHIDIS direct HTTP as a browser/session flow, not as a stable data API.
- Treat authority pages as discovery/supporting evidence, not final status
  verification.
- Keep Playwright as audit/proof tooling until a visible official row and
  attachment listing are proven.

## Discoveries and Risks

- ESHIDIS public works search uses Oracle ADF/session behavior and JavaScript.
- Python in this environment fails TLS verification for tested public HTTPS
  sources unless TLS verification is bypassed; production should use a proper
  CA bundle such as `certifi` or system trust-store configuration.
- Attachment listing from an authority page is possible, but not equivalent to
  listing official ESHIDIS attachments.
- Searching stale or status-mismatched known ids produces no visible official
  row even when the POST is technically correct.

## Outcome

PHASE 1 is partially satisfied: source health, real authority-page tender
reference extraction and ESHIDIS browser form inspection are implemented or
captured. The ESHIDIS attachment listing gate remains blocked pending discovery
of a currently visible official tender row.
