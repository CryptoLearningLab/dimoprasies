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
  - Supports configured `ambiguous_aliases` so uncertain place names can be
    retained for review unless negative context blocks them.

## Attachments and Documents

- `sources download-attachment <eshidis_id>`
  - Downloads one, selected, or all known latest attachment rows.
  - Stores local path, size and SHA-256 in SQLite.
  - Keeps source audit evidence under `work/source_audit/`.
- `sources fetch-kimdis-open-proc`
  - Fetches official KIMDIS attachment URLs for `SUBMISSION_OPEN_CANDIDATE`
    PROC rows from `work/reports/expanded_discovery_report.json`.
  - Stores files under `work/download_audit/kimdis/` with size and SHA-256.
  - Stores extracted text artifacts under `work/extracted_text/kimdis/`.
  - Writes a structured document index at
    `work/derived/kimdis_open_proc_documents.json`.
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
- `entalmata scan`
  - Scans configured Diavgeia organizations from
    `config/diavgeia_entalmata.yml`.
  - Accepts explicit `--max-pages N` for controlled deep/backfill checks
    without changing the normal UI scan depth.
  - Downloads decision PDFs under `work/download_audit/diavgeia_entalmata`.
  - Keeps only configured keyword matches visible for the configured recent
    window, currently 15 days.
  - Archives old visible files under `work/download_audit/diavgeia_entalmata/old`.
  - Stores all state in SQLite table `diavgeia_entalmata`.

## UI Layer

- `/api/dashboard?scope=focus`
  - Combines discovery report rows and SQLite tender metadata.
  - Focus scope uses `config/locations.yml`.
  - Nationwide scope is disabled intentionally until it is redesigned with
    separate state, ESHIDIS-only discovery, and no automatic document/OCR/AI
    processing.
- `/api/document-preview?eshidis_id=...`
  - Lists known latest attachments.
  - Highlights declaration, technical description and budget when present.
  - Serves short text samples only.
- `/api/document-file?attachment_id=...`
  - Serves a downloaded local file only if it exists under `work/`.
- `/api/kimdis-document-preview?official_id=...`
  - Serves the structured KIMDIS preview from
    `work/derived/kimdis_open_proc_documents.json`.
  - Includes local availability, SHA-256, short text sample and document
    authority/scope evidence.
- `/api/kimdis-document-file?official_id=...`
  - Serves a fetched KIMDIS local file only if it exists under `work/`.
- `/api/entalmata`
  - Returns the current recent Diavgeia entalmata list and summary metrics from
    SQLite, including visible and archived counts.
- `/api/entalmata-file?ada=...`
  - Serves the retained local or archived PDF evidence for a Diavgeia entalma
    row when the file exists.
- `/api/entalmata/scan`
  - Starts a background Diavgeia entalmata scan using the configured
    organizations and keyword list.

## Current Presentation Rules

- The first UI screen is a business-facing tender list.
- Geographic focus is configuration-driven.
- Ambiguous place names are recall-first and may appear with match notes.
- Content matches and status verification remain separate.
- Preview depends on known/downloaded attachments; missing files stay visible
  instead of being hidden.
