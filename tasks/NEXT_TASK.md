# NEXT TASK

Execute:
`Configure stable HTTPS access for the droplet UI`

## Current Input

The independent DigitalOcean droplet is running the Tender Radar UI at:

```text
http://165.227.143.152:8765/
```

The UI is production-like and persistent, but browser access is currently plain
HTTP on an IP address. Mobile browsers correctly show this as not secure.

Email alerts are configured and verified:

- SMTP env keys are present on the droplet.
- Real scheduled-run smoke sent 33 rows successfully.
- SQLite `notification_log` recorded 33 sent rows after success.
- `tender-radar-scheduled.timer` is enabled and active.
- The timer cadence is every 6 hours.

## Instruction

Implement the next small gate:

1. Pick the least-surprising HTTPS path:
   - preferred: user-owned domain/subdomain with DNS `A` record to
     `165.227.143.152`;
   - fallback: a temporary wildcard DNS hostname such as `sslip.io` only if the
     user approves it.
2. Install and configure a reverse proxy, preferably Caddy, on the droplet.
3. Proxy HTTPS traffic to the existing local UI service on `127.0.0.1:8765`.
4. Keep the UI service unchanged unless a proxy compatibility issue requires a
   narrowly scoped fix.
5. Confirm HTTP to HTTPS behavior and browser-safe TLS.

## Required Closeout

1. Report the final HTTPS URL.
2. Run curl checks for HTTP/HTTPS status.
3. Confirm `tender-radar-ui.service` remains active.
4. Confirm `tender-radar-scheduled.timer` remains enabled and active.
5. Update `docs/PROGRESS.md`.
6. Update `docs/DECISIONS.md` only if a real decision was made.
7. Update this file with the next single executable gate.
8. Update `docs/HANDOFF.md` if project state or next gate changed.
9. Commit and push tracked changes to GitHub unless explicitly told not to.
