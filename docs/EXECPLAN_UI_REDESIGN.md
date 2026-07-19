# ExecPlan - Human Friendly Tender UI

## Purpose

Make the local Tender Radar UI understandable for non-technical users while
preserving the existing source, download, analysis, evaluation and status
mechanisms.

## Current State

The existing UI exposes backend phases directly: Discovery, Tender, Rules and
Reports. This is useful for development but hard to understand as a daily
workflow. The backend already has:

- `sources discover-active`
- `sources fetch-resource`
- `sources download-attachment`
- `documents analyze`
- `search run`
- `evaluate run`
- `status verify`
- SQLite tender/attachment/document metadata
- JSON/Markdown reports under `work/reports/`

## Scope

Add a clearer first screen:

- default focus on configured local-interest geography,
- optional "all Greece" scope,
- tender list with essential fields,
- eProcurement official link,
- `Download files` action,
- `Preview` for declaration, technical description and budget where present.

Do not change scraping/status logic. Do not mark candidates as verified active.

## Milestones

1. Load geographic focus from config, not hardcoded core constants.
2. Add UI API payload for business-facing tender cards/table.
3. Add basic document preview/download links for already known attachments.
4. Redesign HTML/CSS/JS around the workflow.
5. Run tests and update project docs.

## Data and Interfaces

- `config/locations.yml` remains the source of local geography.
- `/api/dashboard?scope=focus` returns list data. The former `all` scope was
  removed after the redesign because nationwide discovery needs a separate
  safe product gate.
- `/api/document-preview?eshidis_id=...` returns basic document attachments.
- `/api/document-file?attachment_id=...` serves a downloaded local file only.

## Validation

- Unit tests for content types and UI helper behavior.
- Full `.venv/bin/python -m pytest`.
- Manual local UI smoke test with `curl`.

## Progress

- Started: 2026-07-17.
- Added local-interest geography to `config/locations.yml`.
- Added `/api/dashboard`, `/api/document-preview` and `/api/document-file`.
- Reworked the first UI screen into a tender list with focus/all scope,
  official ESHIDIS links, download action and document preview.
- Added helper tests for budget parsing, focus matching and preview payload
  truncation.

## Decisions

- The first screen may filter and present discovered/imported candidates by
  configured geography, but it must not claim national completeness or verified
  active status.

## Discoveries and Risks

- Discovery grid rows have limited structured fields. Official detail fetches
  provide stronger budget/region/authority metadata.
- Preview depends on already downloaded files; otherwise the UI should show
  attachment names and ask for download.

## Outcome

Completed for the first usable UI redesign milestone. The UI now presents the
existing mechanisms through a clearer business-facing first screen. Full test
suite passed with `44 passed`.
