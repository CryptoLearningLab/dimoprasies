# Public Works Tender Radar

Extensible scaffold for monitoring Greek public works tenders from public sources.

This repository is currently after **Phase 1: Source Audit** with a partial
**Phase 2: SQLite Vertical Slice**. It provides the application skeleton,
configuration validation, structured logging, a database schema, source health
checks, browser-backed direct ESHIDIS resource fetch, controlled attachment
download with SHA-256 storage, document classification, optional PDF text
extraction, placeholder scan/search/export commands and tests. It does not yet
claim broad ESHIDIS coverage.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
tender-radar --help
tender-radar config validate
tender-radar sources health
tender-radar db init
```

## Local UI

For daily use on Windows, double-click:

```text
Tender Radar UI.cmd
```

It starts a local browser UI at `http://127.0.0.1:8765/` with buttons for:

- active candidate discovery,
- official ESHIDIS detail fetch,
- attachment download,
- document analysis,
- profile search,
- editable evaluation rules.

The UI uses the same audited CLI commands and stores the same JSON/Markdown
reports under `work/reports/`.

The first screen is now organized for daily use: it defaults to the configured
local-interest geography in `config/locations.yml`, offers an `all Greece`
toggle, shows the essential tender fields, links to the official ESHIDIS
resource page, and provides `Download files` plus preview of declaration,
technical description and budget when those attachments are known.

For private remote access through Tailscale, use:

```text
Tender Radar UI - Tailscale.cmd
```

Keep the launcher window open. It prints the Tailscale URL, usually like
`http://100.x.y.z:8765/`. Open that URL from a phone or laptop that is connected
to the same Tailscale tailnet. Do not expose this UI through public
QuickConnect or router port forwarding.

If Tailscale is not installed on the PC but a Synology or another device
advertises the office LAN as a Tailscale subnet route, use:

```text
Tender Radar UI - LAN.cmd
```

Then open `http://<office-pc-lan-ip>:8765/` from a device connected through
that private route.

For a continuous Synology-hosted setup, use Container Manager or Docker Compose
with `compose.yaml`. See `docs/SYNOLOGY_DEPLOY.md`. With Synology Tailscale IP
`100.75.121.82`, the expected private URL is:

```text
http://100.75.121.82:8765/
```

Without installing the console script, the CLI can also run directly:

```powershell
python -m tender_radar --help
python -m tender_radar config validate
```

## Current CLI

- `config validate` validates repository YAML configuration files.
- `db schema` prints the SQLite schema draft.
- `db init` initializes the SQLite database.
- `sources health` checks the audited public ESHIDIS entry point.
- `sources discover-active` audits the public ESHIDIS search grid for rows
  under the `ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ` status and writes active-candidate reports.
- `sources fetch-resource` fetches one official ESHIDIS resource URL, saves
  audit evidence and imports tender/attachment metadata into SQLite.
- `sources download-attachment` downloads one, selected, or all known
  attachment rows, saves audit evidence and imports file metadata into SQLite.
- `sources import-resource-audit` imports official ESHIDIS resource audit JSON
  into SQLite.
- `sources import-download-audit` imports one audited ESHIDIS attachment
  download result into SQLite.
- `documents analyze` classifies downloaded files, extracts full text where
  supported, stores text artifacts and writes JSON/Markdown reports.
- `search run` applies a YAML search profile to analyzed document text and
  writes search hits with evidence snippets.
- `evaluate run` applies editable YAML evaluation rules with phrases, numeric
  thresholds and scores, then writes a tender-level evaluation report.
- `status verify` writes an advisory status-verification report for one tender
  from the official deadline, latest attachment names and analyzed document
  signals; it does not mutate SQLite tender status or emit `VERIFIED_ACTIVE`.
- `scan`, `download`, `search`, `export` and `status-check` are placeholders
  that intentionally fail until their later phase gates are complete.

## Editable Evaluation Rules

The default dynamic profile is:

```text
config/evaluation_profiles/public_works_dynamic.yml
```

You can edit it from the UI under `Rules`: choose the profile, load it, change
phrases, document types, scores, severity, or numeric filters such as
`εκσκαφές θεμελίων > 5`, then press `Apply Rule` and `Save Rules`. The same
profile is used by the CLI:

```powershell
tender-radar evaluate run --profile config\evaluation_profiles\public_works_dynamic.yml --eshidis-id 221744
```

## Browser Source Audit

The ESHIDIS public works search is an Oracle ADF browser/session flow. For
network inspection:

```powershell
python -m pip install -e ".[browser]"
python -m pip install -e ".[docs]"
$env:NODE_OPTIONS="--use-system-ca"
python -m playwright install chromium
python tools\eshidis_browser_audit.py --eshidis-id 219879 --allow-insecure-tls
python tools\eshidis_resource_audit.py 221744 --allow-insecure-tls
tender-radar sources import-resource-audit work\source_audit\eshidis_resource_audit_221744_full.json --db data\tender_radar.sqlite
python tools\eshidis_download_audit.py 221744 --row-index 0 --allow-insecure-tls
tender-radar sources import-download-audit work\source_audit\eshidis_download_audit_221744_0.json --db data\tender_radar.sqlite
```

Audit JSON and screenshots are written under `work/source_audit/`. Downloaded
audit files are written under `work/download_audit/`.

The same proven flow is now available through the main CLI:

```powershell
$env:NODE_OPTIONS="--use-system-ca"
tender-radar sources discover-active --allow-insecure-tls --limit 25 --report work\reports\eshidis_active_candidates.json --markdown-report work\reports\eshidis_active_candidates.md
tender-radar sources fetch-resource 221744 --allow-insecure-tls
tender-radar sources download-attachment 221744 --row-index 0 --allow-insecure-tls
tender-radar sources download-attachment 221744 --all --limit 8 --allow-insecure-tls
tender-radar documents analyze --eshidis-id 221744 --report work\reports\document_analysis_221744.json --markdown-report work\reports\document_analysis_221744.md
tender-radar search run --profile config\search_profiles\road_maintenance.yml --eshidis-id 221744 --report work\reports\search_road_maintenance_221744.json --markdown-report work\reports\search_road_maintenance_221744.md
tender-radar status verify --eshidis-id 221744 --report work\reports\status_verification_221744.json --markdown-report work\reports\status_verification_221744.md
```

Repeated resource fetches keep existing attachment download metadata when the
same original filename is still present. Repeated bulk downloads skip files
that already have a local path and SHA-256 unless `--force` is used.

Full extracted text is written under `work/extracted_text/`; SQLite stores the
artifact path and a short sample for reports.

The proven first adapter target is:

```text
http://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{eshidis_id}
```

## Project Rules

- Public data only.
- No authentication or CAPTCHA bypass.
- Source families and local authority pages are listed in
  `config/sources.yml` and `docs/SOURCE_WHITELIST.md`.
- Search-specific terms live in runtime requests or YAML profiles, not in the
  core package.
- Content matches and verified active tenders are separate states.
- Deduplication must follow `docs/DEDUPLICATION.md`; title-only matching is
  never enough to merge tender records.
- Unknown values remain `null`, `UNKNOWN`, or explicitly uncertain.
