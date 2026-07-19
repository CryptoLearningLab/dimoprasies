# NEXT TASK

Execute:
`Implement KIMDIS connected-acts forced ESHIDIS lookup`

## Current Input

The verified-link persistence gate is implemented locally:

- UI package version: `0.1.15`;
- SQLite table `verified_tender_links` stores verified source-row to ESHIDIS
  relations;
- candidate enrichment persists a link only after official ESHIDIS fetch
  succeeds;
- dashboard duplicate suppression uses persisted verified links only;
- non-ESHIDIS rows without verified links remain visible as
  `NO_VERIFIED_ESHIDIS_LINK` review candidates;
- local verification passed:
  - `py_compile`;
  - focused DB/UI tests: `97 passed`;
  - full test suite: `183 passed`;
  - no-discovery dashboard smoke: `duplicate_hidden 0`,
    `non_verified_review 29`.
- deployed version: `0.1.15`;
- droplet smoke without full discovery: package version `0.1.15`,
  `verified_links 0`, `duplicate_hidden 0`, `non_verified_review 22`;
- HTTPS shell is live and private APIs still require login:
  `/` returned `200`, `/api/dashboard` returned `401` without a session.
- UI package version `0.1.16` adds strong explicit linked-id duplicate
  suppression: non-ESHIDIS rows with an explicit linked official ESHIDIS id are
  hidden when at least two fields match the official row among title, deadline,
  budget and authority. Local no-discovery smoke reported `duplicate_hidden 8`
  and `non_verified_review 21`.

## Instruction

Implement the next small gate:

1. Add a public KIMDIS connected-acts lookup for `26PROC...` ADAM values using
   the Promitheus page:
   `https://cerpp.eprocurement.gov.gr/upgkimdis/unprotected/home.xhtml?cid=3`.
2. Use only public, read-only access. Do not bypass login, CAPTCHA or technical
   restrictions.
3. For a KIMDIS row, submit or reproduce the connected-acts search for its
   `26PROC...` ADAM and collect linked official acts/documents.
4. Download/open only the returned public documents needed for evidence.
5. Extract candidate ESHIDIS ids from connected acts, declarations, summaries,
   economic-offer forms, links and text around ESHIDIS wording.
6. Verify each candidate id through:
   `https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{id}`.
7. Persist only verified results in SQLite `verified_tender_links`.
8. Keep KIMDIS rows visible as review candidates when no verified ESHIDIS link
   can be proven.
9. Do not use title-only deduplication.

## Required Tests

Add focused tests for:

- connected-acts request construction/parsing from a fixture or mocked response;
- extraction of ESHIDIS ids from connected-act document text/links;
- successful verification persists `verified_tender_links`;
- failed/no-match lookup keeps the source row as `NO_VERIFIED_ESHIDIS_LINK`;
- dashboard still prefers the official ESHIDIS row only after verified
  persistence.

## Required Closeout

1. Run focused tests and full test suite.
2. Run a local or droplet smoke without full discovery.
3. Report how many KIMDIS rows gained verified ESHIDIS links and how many
   remain review candidates.
4. Update `docs/PROGRESS.md`.
5. Update `docs/DECISIONS.md` only if a real decision was made.
6. Update `docs/HANDOFF.md`.
7. Update this file with the next single executable gate.
8. Commit and push tracked changes to GitHub unless explicitly told not to.
