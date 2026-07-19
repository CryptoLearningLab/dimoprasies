# NEXT TASK

Execute:
`Verify and deploy deadline-evidence dashboard gate`

## Current Input

The deadline-evidence dashboard gate is implemented locally in UI package
version `0.1.19`.

- `dashboard_payload` enriches rows with fetched document evidence before
  active filtering.
- `document_evidence_payload` extracts candidate submission deadlines from
  declaration-like document text, including Greek deadline/offer/extension
  contexts.
- `dashboard_row_is_active` no longer treats unknown deadlines as active.
  Rows without a direct, linked-official or document-derived parseable deadline
  are hidden from the main dashboard.
- Focused local UI tests passed: `tests/test_ui_server.py` -> `92 passed`.

## Instruction

Complete the closeout gate:

1. Run the full local test suite.
2. Run a local no-discovery dashboard smoke.
3. Commit and push tracked changes.
4. Let the GitHub deploy workflow update the DigitalOcean droplet.
5. Smoke the production droplet without full discovery:
   - homepage returns `v0.1.19`;
   - private dashboard API is still `401` without login;
   - runtime dashboard smoke reports visible count, expired hidden count and
     visible unknown-deadline count.
6. Confirm visible unknown-deadline count is zero.
7. Report any remaining rows hidden because they need deadline evidence.

## Required Tests

- Full `pytest`.
- No-discovery dashboard smoke.
- Production smoke after deploy.

## Required Closeout

1. Update `docs/PROGRESS.md` with full-suite and production smoke evidence.
2. Update `docs/HANDOFF.md` if production/deployment state changes.
3. Update this file with the next single executable gate.
4. Do not run full discovery unless explicitly requested.
