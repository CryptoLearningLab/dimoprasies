# NEXT TASK

Execute:
`Harden document fetcher for new or suspect rows`

## Current Input

The first infrastructure gates are now in place:

- stable droplet runtime,
- runtime `.env.local` with OpenAI and SMTP settings,
- SQLite source/dismissal/notification state,
- per-source poller with skip behavior,
- production email alerts,
- 6-hour systemd timer,
- Caddy HTTPS access at `https://165.227.143.152.sslip.io/`.

The next product gate is document fetching. The system already has per-row
fetch/zip behavior and ESHIDIS attachment download mechanisms, but the
production scheduler needs a stricter document fetcher contract for new or
suspect non-ESHIDIS rows.

## Instruction

Implement the next small gate:

1. Identify the current document fetch paths for:
   - ESHIDIS rows,
   - KIMDIS rows,
   - municipal/regional authority rows.
2. Ensure the scheduled path downloads documents only for rows that are new,
   changed, unprocessed, or explicitly suspect.
3. Persist document provenance in SQLite or a clearly documented migration
   bridge:
   - source row key,
   - source URL,
   - document URL,
   - local path,
   - SHA-256,
   - fetched timestamp,
   - fetch error when applicable.
4. Preserve originals; do not delete previously downloaded files.
5. Add focused tests for skip vs fetch decisions.

## Required Closeout

1. Run targeted tests for the document fetcher changes.
2. Run the full test suite if app code changes.
3. Run one droplet smoke that proves unchanged rows do not re-download.
4. Report changed files and verification commands.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
