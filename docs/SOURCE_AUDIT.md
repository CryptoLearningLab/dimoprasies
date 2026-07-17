# Source Audit

Date: 2026-07-17

## Summary

The public ESHIDIS works search URL is reachable, but it behaves like an Oracle
ADF browser/session application rather than a simple static API. Direct HTTP can
obtain an entry response/session evidence, but reliable search and attachment
listing need browser automation or a discovered stable endpoint.

This audit added a minimal source health check, an authority-page extraction
proof, repeatable Playwright browser inspection scripts and a proven direct
ESHIDIS public resource detail/attachment listing. A production scan adapter is
still pending, but the PHASE 1 official-source proof is satisfied.

Discovery update 2026-07-17: `sources discover-active` can submit the public
status filter value `2` and parse tender rows from hidden Oracle ADF XML
responses. The latest audit produced 15 `DISCOVERED_ACTIVE_CANDIDATE` ids, but
each id still requires `resources/search/{eshidis_id}` verification before the
project may use `VERIFIED_ACTIVE`.

## Sources Checked

### ESHIDIS Public Works Active Search

URL:
`https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/active_search_main.jspx`

Observed behavior:
- `Invoke-WebRequest` with real network access returned HTTP 200.
- The response included Oracle ADF loopback JavaScript and a `jsessionid`.
- A no-JavaScript client can receive the message that JavaScript is required.
- Python `urllib` with default TLS verification failed in this environment with
  `CERTIFICATE_VERIFY_FAILED`.
- Python `urllib` with audit-only TLS bypass returned HTTP 200 and session
  evidence.

Conclusion:
- Treat the URL as browser/session flow.
- Do not implement direct crawler assumptions yet.
- Browser inspection is required for result and attachment data.

### ESHIDIS Browser Inspection

Tool:
`tools/eshidis_browser_audit.py`

Observed behavior:
- Playwright Chromium can load the public form and pass the Oracle ADF loopback
  page.
- Page title/body contains `Αναζήτηση Διαγωνισμών Δημοσίων Έργων`.
- Status select field id: `qryId1:val00::content`.
- Default status value: `2`, displayed as `ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ`.
- ESHIDIS system id input: `qryId1:val10::content`.
- Search button id: `qryId1::search`.
- Search sends an ADF POST to `active_search_main.jspx` with fields including
  `javax.faces.ViewState`, `Adf-Window-Id`, `qryId1:val00` and `qryId1:val10`.

Known-id probes:
- `219879` with status values `1`, `2`, `3` and `4`.
- `221439`, `221684` and `219756` with status value `2`.

Result:
- The browser flow and POST payload are reproducible.
- The known ids were submitted in POST data.
- No official result row or attachment listing was returned for the tested
  status/id combinations.

Likely explanation:
- The authority-page sample `219879` had a stated submission deadline of
  `29/04/2026 15:00`, so it is not expected to appear under the default active
  submission status on `2026-07-17`.
- The remaining ids may belong to other statuses or may require broader search
  criteria before drilling into a row.

Conclusion:
- ESHIDIS form search automation is feasible, but the direct public resource URL
  is a better first adapter target than the search grid.
- Do not enable broad `scan` until `resources/search/{eshidis_id}` retrieval is
  implemented and tested as a read-only adapter.

### ESHIDIS Direct Public Resource Proof

Tool:
`tools/eshidis_resource_audit.py`

Observed direct URL:
`http://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/221744`

Redirect behavior:
- HTTP resource URL redirects to HTTPS.
- HTTPS resource URL redirects to an Oracle ADF task-flow detail page with
  `auctionId=221744`.

Official tender fields captured:
- Title: `ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027`
- ESHIDIS id: `221744`
- CPV: `45233141-9`
- Authority: `ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΟΣ`
- Location: `EL631 - Αιτωλοακαρνανία (Aitoloakarnania)`
- Budget with VAT: `2.500.000,00`
- Publication date: `15-07-2026 00:44:36`
- Submission deadline: `07-08-2026 10:00:00`

Attachment listing:
- Clicking `Συνημμένα Αρχεία` returned an ADF XML table with `_rowCount="8"`.
- Attachment rows include PDF/XML filenames and `Λήψη` controls.
- This proves official attachment listing without private login.

Conclusion:
- `resources/search/{eshidis_id}` is the first stable public-source adapter
  target.
- Attachment download actions still need a separate audit before Phase 3/4.

### Public Authority Sample — Δήμος Μεγαλόπολης

Public page:
`https://megalopoli.gov.gr/διακήρυξη-ανοικτού-ηλεκτρονικού-δια/`

Observed public fields:
- Tender title: `ΔΙΑΜΟΡΦΩΣΗ ΟΔΟΥ ΠΡΟΣΒΑΣΗΣ Δ.ΚΟΙΜΗΤΗΡΙΟΥ Δ.ΜΕΓΑΛΟΠΟΛΗΣ`
- Budget: `188.000,00€` with VAT
- ESHIDIS system id: `219879`
- Submission deadline stated on authority page: `29/04/2026 15:00`
- One PDF attachment link was extracted from the page.

Conclusion:
- Authority pages can provide discovery evidence and attachment fallback.
- They must not replace ESHIDIS/KIMDIS status verification.

## Implemented Proof

New module:
`src/tender_radar/sources/eshidis.py`

Capabilities:
- `health_check()` checks the public ESHIDIS entry point.
- `inspect_eshidis_html()` classifies Oracle ADF/JavaScript/session behavior.
- `inspect_authority_page()` extracts a tender title, ESHIDIS id and attachment
  links from a public authority page.
- `parse_eshidis_resource_text()` extracts official tender detail fields from
  the public resource page text.
- `parse_eshidis_attachment_xml()` extracts attachment row count and filenames
  from the ADF attachment table response.

New CLI:

```powershell
tender-radar sources health
tender-radar sources health --allow-insecure-tls
```

The `--allow-insecure-tls` flag is for audit diagnosis only. Production code
should use a correct CA bundle/trust-store configuration.

Browser audit helper:

```powershell
python tools\eshidis_browser_audit.py --eshidis-id 219879 --allow-insecure-tls
python tools\eshidis_resource_audit.py 221744 --allow-insecure-tls
```

Useful environment note:

```powershell
$env:NODE_OPTIONS="--use-system-ca"
python -m playwright install chromium
```

## Evidence

PHASE 1 gate:

```text
python -m pytest
7 passed

tender-radar config validate
all config files OK
```

Live ESHIDIS health with default TLS:

```json
{
  "reachable": false,
  "message": "HTTP failure: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] ...>"
}
```

Live ESHIDIS health with audit TLS bypass:

```json
{
  "reachable": true,
  "status_code": 200,
  "session_hint": true,
  "message": "Endpoint reachable. TLS verification was disabled for audit."
}
```

Authority page extraction proof:

```text
eshidis_id='219879'
attachment_links=('https://megalopoli.gov.gr/wp-content/uploads/2026/04/ΠΕΡΙΛΗΨΗ-ΔΙΑΚΗΡΥΞΗ-ΔΙΑΜΟΡΦΩΣΗ-ΟΔΟΥ-ΠΡΟΣΒΑΣΗΣ-Δ_ΚΟΙΜΗΤΗΡΙΟΥ-ΜΕ-ΨΗΦΙΑΚΗ.pdf',)
```

Official direct resource proof:

```text
resources/search/221744
title='ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027'
cpv='45233141-9'
submission_deadline='07-08-2026 10:00:00'
attachment_rows=8
```

## Blockers

- Direct resource details and attachment listing are proven for one live tender.
- File download from the `Λήψη` controls has not yet been implemented.
- Python TLS trust must be fixed before production HTTPS retrieval.
- Form-grid search remains less reliable than direct resource URLs and should be
  treated as a later discovery path.

## Next Recommendation

Continue with a read-only adapter task:

1. Implement `resources/search/{eshidis_id}` retrieval through Playwright or a
   compatible HTTP client.
2. Persist tender details and attachment metadata to SQLite.
3. Keep file downloads disabled until the `Λήψη` action is audited.
4. Add TEE subscription platform as a future authenticated source candidate,
   with credentials handled outside repository files.
