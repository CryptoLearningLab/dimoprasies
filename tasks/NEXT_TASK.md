# NEXT TASK

Execute:
`Verify and deploy KIMDIS connected-acts forced ESHIDIS lookup`

## Current Input

The KIMDIS connected-acts gate is implemented locally in UI package version
`0.1.18`.

- `src/tender_radar/sources/kimdis_connected_acts.py` uses the public read-only
  KIMDIS Open Data endpoint:
  `https://cerpp.eprocurement.gov.gr/khmdhs-opendata/adamChain/{referenceNumber}`.
- Connected KIMDIS acts are mapped to public attachment endpoints such as
  `/notice/attachment/{referenceNumber}` and `/request/attachment/{referenceNumber}`.
- `run_selected_fetch` falls back to connected acts for `26PROC...` rows when
  the normal KIMDIS document index has no linked ESHIDIS id.
- Connected-acts evidence is merged into
  `work/derived/kimdis_open_proc_documents.json`.
- The official ESHIDIS fetch path still verifies discovered ids through
  `pwgopendata` before candidate enrichment persists verified links.
- Focused local tests passed:
  `tests/test_kimdis_connected_acts.py`,
  `tests/test_kimdis_fetch.py`,
  `tests/test_ui_server.py` -> `110 passed`.
- Live source smoke without full discovery found:
  - `26PROC019367864 -> 221566`
  - `26PROC019417347 -> 221691`

## Instruction

Complete the closeout gate:

1. Run the full local test suite.
2. Run a local no-discovery dashboard smoke.
3. Commit and push tracked changes.
4. Let the GitHub deploy workflow update the DigitalOcean droplet.
5. Smoke the production droplet without full discovery:
   - homepage returns `v0.1.18`;
   - private dashboard API is still `401` without login;
   - runtime dashboard smoke reports visible count, duplicate hidden count,
     expired hidden count and non-verified KIMDIS/authority review count.
6. Run one safe selected-fetch smoke for a KIMDIS id already known to link
   through connected acts, then verify the dashboard still avoids title-only
   deduplication and keeps rows visible when no verified link exists.
7. Report how many KIMDIS rows gained linked ESHIDIS ids through connected acts
   and how many remain `NO_VERIFIED_ESHIDIS_LINK`.

## Required Tests

- Full `pytest`.
- No-discovery dashboard smoke.
- Production smoke after deploy.

## Required Closeout

1. Update `docs/PROGRESS.md` with full-suite and production smoke evidence.
2. Update `docs/HANDOFF.md` if production/deployment state changes.
3. Update this file with the next single executable gate.
4. Do not run full discovery unless explicitly requested.
