# Available Mechanisms

This document records the mechanisms already available behind the UI. The
human-friendly UI should compose these mechanisms instead of replacing them.

## Source and Discovery

- `sources health`
  - Checks the public ESHIDIS public-works entry point.
- `sources discover-active`
  - Uses the audited Oracle ADF browser flow.
  - Reads candidate rows under `ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ`.
  - Writes JSON/Markdown reports under `work/reports/`.
  - Produces `DISCOVERED_ACTIVE_CANDIDATE`, not `VERIFIED_ACTIVE`.
- `sources fetch-resource <eshidis_id>`
  - Opens the official public ESHIDIS resource detail page.
  - Imports metadata and latest attachment names into SQLite.
  - Preserves existing local download metadata for matching filenames.
- `sources expanded-report`
  - Combines ESHIDIS discovery candidates with KIMDIS Open Data
    PROC/AWRD/SYMV records.
  - Classifies PROC rows by `finalSubmissionDate` as candidate-only submission
    stage.
  - Deduplicates only by official source id.

## Attachments and Documents

- `sources download-attachment <eshidis_id>`
  - Downloads one, selected, or all known latest attachment rows.
  - Stores local path, size and SHA-256 in SQLite.
  - Keeps source audit evidence under `work/source_audit/`.
- `sources fetch-kimdis-open-proc`
  - Fetches official KIMDIS attachment URLs for `SUBMISSION_OPEN_CANDIDATE`
    PROC rows from `work/reports/expanded_discovery_report.json`.
  - Stores files under `work/download_audit/kimdis/` with size and SHA-256.
  - Extracts supported PDF/XML text in-memory for the shortlist report.
  - Records whether document text contains authority/scope evidence from
    `config/sources.yml`.
  - Remains candidate-only and does not emit `VERIFIED_ACTIVE`.
- `documents analyze`
  - Classifies downloaded attachments.
  - Extracts text where supported.
  - Stores full text under `work/extracted_text/`.
  - Writes JSON/Markdown document reports.

## Search, Evaluation and Status

- `search run`
  - Applies YAML search profiles against analyzed document text.
  - Persists search hits with provenance.
- `evaluate run`
  - Applies editable evaluation rules from
    `config/evaluation_profiles/public_works_dynamic.yml`.
  - Supports phrase rules, document type filters, numeric thresholds and
    scoring.
- `status verify`
  - Writes advisory JSON/Markdown status evidence.
  - Checks official deadline, latest attachment names and document signals.
  - Does not mutate `tenders.status`.
  - Does not emit `VERIFIED_ACTIVE`.

## UI Layer

- `/api/dashboard?scope=focus|all`
  - Combines discovery report rows and SQLite tender metadata.
  - Focus scope uses `config/locations.yml`.
  - All-Greece scope shows all known/discovered rows but does not claim
    national completeness.
- `/api/document-preview?eshidis_id=...`
  - Lists known latest attachments.
  - Highlights declaration, technical description and budget when present.
  - Serves short text samples only.
- `/api/document-file?attachment_id=...`
  - Serves a downloaded local file only if it exists under `work/`.

## Current Presentation Rules

- The first UI screen is a business-facing tender list.
- Geographic focus is configuration-driven.
- Content matches and status verification remain separate.
- Preview depends on known/downloaded attachments; missing files stay visible
  instead of being hidden.
