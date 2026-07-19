from __future__ import annotations

import argparse
from datetime import date
import json
import logging
import sys
from pathlib import Path

from tender_radar import __version__
from tender_radar.config import repository_root, validate_repository_configs
from tender_radar.db import (
    AttachmentStatus,
    create_search_run,
    finish_search_run,
    import_attachment_download,
    import_eshidis_resource,
    initialize,
    insert_search_hit,
    list_downloaded_attachments,
    list_latest_attachments,
    list_searchable_documents,
    upsert_document_analysis,
)
from tender_radar.documents import analyze_document, render_markdown_report
from tender_radar.evaluation import evaluate_documents, load_evaluation_profile, render_evaluation_markdown
from tender_radar.logging_config import configure_logging
from tender_radar.matching import load_search_profile, match_profile, render_search_markdown
from tender_radar.sources.eshidis import (
    EshidisAttachmentListing,
    health_check,
    parse_eshidis_attachment_xml,
    parse_eshidis_resource_text,
)
from tender_radar.sources.eshidis_browser import (
    discover_active_candidates_audit,
    download_attachment_audit,
    fetch_resource_audit,
    render_discovery_markdown,
)
from tender_radar.sources.expanded_report import build_expanded_report, write_expanded_report
from tender_radar.sources.kimdis_fetch import (
    fetch_kimdis_open_proc_candidates,
    write_kimdis_document_index,
    write_kimdis_fetch_report,
)
from tender_radar.sources.whitelist import audit_source_whitelist, write_source_audit_report
from tender_radar.status import verify_tender_status, write_status_reports

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tender-radar",
        description="Public works tender monitoring tool.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable debug JSON logs.")
    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser("config", help="Configuration commands.")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("validate", help="Validate YAML configuration files.")

    db_parser = subparsers.add_parser("db", help="Database commands.")
    db_sub = db_parser.add_subparsers(dest="db_command")
    db_sub.add_parser("schema", help="Print SQLite schema draft.")
    db_init = db_sub.add_parser("init", help="Initialize SQLite database.")
    db_init.add_argument("--path", default="data/tender_radar.sqlite", help="SQLite database path.")

    runtime_parser = subparsers.add_parser("runtime", help="Runtime automation commands.")
    runtime_sub = runtime_parser.add_subparsers(dest="runtime_command")
    scheduled_run = runtime_sub.add_parser(
        "scheduled-run",
        help="Run bounded poll, AI triage, enrichment and email alert sequence.",
    )
    scheduled_run.add_argument("--scope", choices=["focus"], default="focus")
    scheduled_run.add_argument("--sort", choices=["deadline_asc", "budget_desc"], default="deadline_asc")
    scheduled_run.add_argument("--limit", type=int, default=100, help="Bounded ESHIDIS discovery limit.")
    scheduled_run.add_argument("--ai-batch-size", type=int, default=20)
    scheduled_run.add_argument("--enrichment-limit", type=int, default=50)
    scheduled_run.add_argument("--recipient", default=None, help="Override alert recipient.")
    scheduled_run.add_argument("--dry-run", action="store_true", help="Do not send email or mutate notification state.")
    scheduled_run.add_argument(
        "--report",
        default="work/reports/scheduled_poll_alert_latest.json",
        help="JSON audit report output path.",
    )
    scheduled_run.add_argument(
        "--markdown-report",
        default="work/reports/scheduled_poll_alert_latest.md",
        help="Markdown audit report output path.",
    )

    documents_parser = subparsers.add_parser("documents", help="Document analysis commands.")
    documents_sub = documents_parser.add_subparsers(dest="documents_command")
    documents_analyze = documents_sub.add_parser(
        "analyze",
        help="Classify downloaded documents and extract text where supported.",
    )
    documents_analyze.add_argument("--eshidis-id", default=None, help="Analyze one ESHIDIS tender id.")
    documents_analyze.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    documents_analyze.add_argument(
        "--report",
        default=None,
        help="JSON report output path.",
    )
    documents_analyze.add_argument(
        "--markdown-report",
        default=None,
        help="Markdown report output path.",
    )
    documents_analyze.add_argument(
        "--text-dir",
        default="work/extracted_text",
        help="Directory for full extracted text artifacts.",
    )

    search_parser = subparsers.add_parser("search", help="Search analyzed documents.")
    search_sub = search_parser.add_subparsers(dest="search_command")
    search_run = search_sub.add_parser("run", help="Run a YAML search profile against analyzed documents.")
    search_run.add_argument("--profile", required=True, help="Path to search profile YAML.")
    search_run.add_argument("--eshidis-id", default=None, help="Limit search to one ESHIDIS tender id.")
    search_run.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    search_run.add_argument("--report", default=None, help="JSON report output path.")
    search_run.add_argument("--markdown-report", default=None, help="Markdown report output path.")

    evaluate_parser = subparsers.add_parser("evaluate", help="Dynamic tender evaluation commands.")
    evaluate_sub = evaluate_parser.add_subparsers(dest="evaluate_command")
    evaluate_run = evaluate_sub.add_parser("run", help="Run editable evaluation rules against analyzed documents.")
    evaluate_run.add_argument("--profile", required=True, help="Path to evaluation profile YAML.")
    evaluate_run.add_argument("--eshidis-id", default=None, help="Limit evaluation to one ESHIDIS tender id.")
    evaluate_run.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    evaluate_run.add_argument("--report", default=None, help="JSON report output path.")
    evaluate_run.add_argument("--markdown-report", default=None, help="Markdown report output path.")

    status_parser = subparsers.add_parser("status", help="Status verification commands.")
    status_sub = status_parser.add_subparsers(dest="status_command")
    status_verify = status_sub.add_parser(
        "verify",
        help="Write an advisory status-verification report for one tender.",
    )
    status_verify.add_argument("--eshidis-id", required=True, help="ESHIDIS tender id.")
    status_verify.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    status_verify.add_argument("--report", default=None, help="JSON report output path.")
    status_verify.add_argument("--markdown-report", default=None, help="Markdown report output path.")

    entalmata_parser = subparsers.add_parser("entalmata", help="Diavgeia warrant/payment decision commands.")
    entalmata_sub = entalmata_parser.add_subparsers(dest="entalmata_command")
    entalmata_scan = entalmata_sub.add_parser(
        "scan",
        help="Scan Diavgeia decisions for configured warrant keywords and keep the recent window.",
    )
    entalmata_scan.add_argument("--config", default="config/diavgeia_entalmata.yml", help="Entalmata YAML config path.")
    entalmata_scan.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    entalmata_scan.add_argument("--download-dir", default="work/download_audit/diavgeia_entalmata", help="PDF storage path.")
    entalmata_scan.add_argument("--report", default="work/reports/diavgeia_entalmata_latest.json", help="JSON report output path.")

    sources_parser = subparsers.add_parser("sources", help="Source audit commands.")
    sources_sub = sources_parser.add_subparsers(dest="sources_command")
    sources_health = sources_sub.add_parser("health", help="Run source health checks.")
    sources_health.add_argument(
        "--allow-insecure-tls",
        action="store_true",
        help="Disable TLS verification for source-audit diagnosis only.",
    )
    audit_whitelist = sources_sub.add_parser(
        "audit-whitelist",
        help="Check configured source whitelist reachability and adapter readiness.",
    )
    audit_whitelist.add_argument("--config", default="config/sources.yml", help="Source whitelist YAML path.")
    audit_whitelist.add_argument(
        "--report",
        default="work/reports/source_whitelist_audit.json",
        help="JSON report output path.",
    )
    audit_whitelist.add_argument(
        "--markdown-report",
        default="work/reports/source_whitelist_audit.md",
        help="Markdown report output path.",
    )
    audit_whitelist.add_argument("--timeout", type=int, default=20, help="Per-source timeout in seconds.")
    audit_whitelist.add_argument("--allow-insecure-tls", action="store_true")
    expanded_report = sources_sub.add_parser(
        "expanded-report",
        help="Build a controlled expanded discovery report from ESHIDIS candidates and KIMDIS Open Data.",
    )
    expanded_report.add_argument("--config", default="config/sources.yml", help="Source whitelist YAML path.")
    expanded_report.add_argument(
        "--eshidis-candidates",
        default="work/reports/eshidis_active_candidates.json",
        help="ESHIDIS candidates JSON path to include.",
    )
    expanded_report.add_argument("--kimdis-pages", type=int, default=20, help="KIMDIS pages per record family.")
    expanded_report.add_argument(
        "--kimdis-source-id",
        action="append",
        default=None,
        help="Fetch only the selected KIMDIS family id. Repeatable; omitted means all families.",
    )
    expanded_report.add_argument(
        "--authority-limit-per-source",
        type=int,
        default=20,
        help="Maximum municipal/authority listing rows to extract per configured source.",
    )
    expanded_report.add_argument(
        "--authority-source-id",
        action="append",
        default=None,
        help="Fetch only the selected authority adapter id. Repeatable; omitted means all authority sources.",
    )
    expanded_report.add_argument(
        "--previous-report",
        default=None,
        help="Previous expanded report used to retain candidates from sources skipped as unchanged.",
    )
    expanded_report.add_argument("--timeout", type=int, default=20, help="Per-request timeout in seconds.")
    expanded_report.add_argument(
        "--as-of-date",
        default=None,
        help="Submission-status cutoff date in YYYY-MM-DD format; defaults to today.",
    )
    expanded_report.add_argument("--allow-insecure-tls", action="store_true")
    expanded_report.add_argument(
        "--report",
        default="work/reports/expanded_discovery_report.json",
        help="JSON report output path.",
    )
    expanded_report.add_argument(
        "--markdown-report",
        default="work/reports/expanded_discovery_report.md",
        help="Markdown report output path.",
    )
    ai_triage = sources_sub.add_parser(
        "ai-triage-report",
        help="Run advisory OpenAI triage over the current dashboard discovery rows.",
    )
    ai_triage.add_argument("--scope", choices=["focus"], default="focus", help="Dashboard scope to triage.")
    ai_triage.add_argument("--sort", choices=["deadline_asc", "budget_desc"], default="deadline_asc")
    ai_triage.add_argument("--model", default=None, help="OpenAI model; defaults to OPENAI_MODEL or gpt-4.1-mini.")
    ai_triage.add_argument("--batch-size", type=int, default=20, help="Rows per OpenAI request.")
    ai_triage.add_argument("--timeout", type=int, default=60, help="OpenAI request timeout in seconds.")
    ai_triage.add_argument(
        "--report",
        default="work/reports/ai_triage_report.json",
        help="JSON report output path.",
    )
    ai_triage.add_argument(
        "--markdown-report",
        default="work/reports/ai_triage_report.md",
        help="Markdown report output path.",
    )
    kimdis_fetch = sources_sub.add_parser(
        "fetch-kimdis-open-proc",
        help="Fetch official attachments for open KIMDIS PROC candidates from an expanded report.",
    )
    kimdis_fetch.add_argument(
        "--expanded-report",
        default="work/reports/expanded_discovery_report.json",
        help="Expanded discovery JSON path.",
    )
    kimdis_fetch.add_argument("--config", default="config/sources.yml", help="Source whitelist YAML path.")
    kimdis_fetch.add_argument(
        "--download-dir",
        default="work/download_audit/kimdis",
        help="Directory for downloaded KIMDIS attachments.",
    )
    kimdis_fetch.add_argument(
        "--text-dir",
        default="work/extracted_text/kimdis",
        help="Directory for extracted KIMDIS text artifacts.",
    )
    kimdis_fetch.add_argument(
        "--document-index",
        default="work/derived/kimdis_open_proc_documents.json",
        help="Structured KIMDIS document index output path.",
    )
    kimdis_fetch.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    kimdis_fetch.add_argument("--limit", type=int, default=50, help="Maximum open PROC candidates to fetch.")
    kimdis_fetch.add_argument(
        "--official-id",
        default=None,
        help="Fetch only one KIMDIS PROC official id, e.g. 26PROC019417347.",
    )
    kimdis_fetch.add_argument("--force", action="store_true", help="Download again even when a local file exists.")
    kimdis_fetch.add_argument("--retries", type=int, default=2, help="Retries for HTTP 429 rate-limit responses.")
    kimdis_fetch.add_argument(
        "--retry-delay",
        type=float,
        default=20.0,
        help="Seconds to wait before retrying after HTTP 429.",
    )
    kimdis_fetch.add_argument(
        "--request-delay",
        type=float,
        default=1.0,
        help="Seconds to wait between attachment requests.",
    )
    kimdis_fetch.add_argument("--allow-insecure-tls", action="store_true")
    kimdis_fetch.add_argument(
        "--report",
        default="work/reports/kimdis_open_proc_fetch_report.json",
        help="JSON report output path.",
    )
    kimdis_fetch.add_argument(
        "--markdown-report",
        default="work/reports/kimdis_open_proc_fetch_report.md",
        help="Markdown report output path.",
    )
    discover_active = sources_sub.add_parser(
        "discover-active",
        help="Audit the public ESHIDIS active-search grid and save active candidate rows.",
    )
    discover_active.add_argument(
        "--status-value",
        default="2",
        help="ESHIDIS status select value; 2 is ΥΠΟΒΟΛΗ ΠΡΟΣΦΟΡΩΝ in the audited form.",
    )
    discover_active.add_argument("--limit", type=int, default=100, help="Maximum candidate rows to extract.")
    discover_active.add_argument(
        "--report",
        default="work/reports/eshidis_active_candidates.json",
        help="JSON report output path.",
    )
    discover_active.add_argument(
        "--markdown-report",
        default="work/reports/eshidis_active_candidates.md",
        help="Markdown report output path.",
    )
    discover_active.add_argument("--allow-insecure-tls", action="store_true")
    discover_active.add_argument("--headful", action="store_true")
    import_audit = sources_sub.add_parser(
        "import-resource-audit",
        help="Import ESHIDIS resource audit JSON into SQLite.",
    )
    import_audit.add_argument("audit_json", help="Path to tools/eshidis_resource_audit.py JSON output.")
    import_audit.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    import_download = sources_sub.add_parser(
        "import-download-audit",
        help="Import one ESHIDIS download audit JSON into SQLite attachment metadata.",
    )
    import_download.add_argument("download_audit_json", help="Path to tools/eshidis_download_audit.py JSON output.")
    import_download.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    fetch_resource = sources_sub.add_parser(
        "fetch-resource",
        help="Fetch one ESHIDIS resource URL, save audit JSON and import tender metadata.",
    )
    fetch_resource.add_argument("eshidis_id", help="ESHIDIS system id.")
    fetch_resource.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    fetch_resource.add_argument("--out", default=None, help="Audit JSON output path.")
    fetch_resource.add_argument("--allow-insecure-tls", action="store_true")
    fetch_resource.add_argument("--headful", action="store_true")
    fetch_resource.add_argument(
        "--no-import",
        action="store_true",
        help="Only save the audit JSON; do not import into SQLite.",
    )
    download_attachment = sources_sub.add_parser(
        "download-attachment",
        help="Download one ESHIDIS attachment row and import file metadata into SQLite.",
    )
    download_attachment.add_argument("eshidis_id", help="ESHIDIS system id.")
    download_attachment.add_argument("--row-index", type=int, default=0, help="Zero-based attachment row index.")
    download_attachment.add_argument(
        "--row-indexes",
        default=None,
        help="Comma-separated zero-based attachment row indexes, e.g. 0,2,4.",
    )
    download_attachment.add_argument(
        "--all",
        action="store_true",
        help="Download all latest attachment rows known in SQLite.",
    )
    download_attachment.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum rows to download in one command.",
    )
    download_attachment.add_argument(
        "--force",
        action="store_true",
        help="Download even when an attachment already has a local file.",
    )
    download_attachment.add_argument("--db", default="data/tender_radar.sqlite", help="SQLite database path.")
    download_attachment.add_argument("--out", default=None, help="Download audit JSON output path.")
    download_attachment.add_argument("--download-dir", default="work/download_audit", help="Downloaded file directory.")
    download_attachment.add_argument("--allow-insecure-tls", action="store_true")
    download_attachment.add_argument("--headful", action="store_true")
    download_attachment.add_argument(
        "--no-import",
        action="store_true",
        help="Only save the download audit JSON; do not import into SQLite.",
    )

    for command in ("scan", "download", "export", "status-check"):
        subparsers.add_parser(command, help=f"{command} placeholder for later phases.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "config" and args.config_command == "validate":
        return _config_validate()
    if args.command == "db" and args.db_command == "schema":
        return _print_schema()
    if args.command == "db" and args.db_command == "init":
        return _db_init(Path(args.path))
    if args.command == "runtime" and args.runtime_command == "scheduled-run":
        return _runtime_scheduled_run(args)
    if args.command == "documents" and args.documents_command == "analyze":
        return _documents_analyze(args)
    if args.command == "search" and args.search_command == "run":
        return _search_run(args)
    if args.command == "evaluate" and args.evaluate_command == "run":
        return _evaluate_run(args)
    if args.command == "status" and args.status_command == "verify":
        return _status_verify(args)
    if args.command == "entalmata" and args.entalmata_command == "scan":
        return _entalmata_scan(args)
    if args.command == "sources" and args.sources_command == "health":
        return _sources_health(args.allow_insecure_tls)
    if args.command == "sources" and args.sources_command == "audit-whitelist":
        return _sources_audit_whitelist(args)
    if args.command == "sources" and args.sources_command == "expanded-report":
        return _sources_expanded_report(args)
    if args.command == "sources" and args.sources_command == "ai-triage-report":
        return _sources_ai_triage_report(args)
    if args.command == "sources" and args.sources_command == "fetch-kimdis-open-proc":
        return _sources_fetch_kimdis_open_proc(args)
    if args.command == "sources" and args.sources_command == "discover-active":
        return _sources_discover_active(args)
    if args.command == "sources" and args.sources_command == "import-resource-audit":
        return _sources_import_resource_audit(Path(args.audit_json), Path(args.db))
    if args.command == "sources" and args.sources_command == "import-download-audit":
        return _sources_import_download_audit(Path(args.download_audit_json), Path(args.db))
    if args.command == "sources" and args.sources_command == "fetch-resource":
        return _sources_fetch_resource(args)
    if args.command == "sources" and args.sources_command == "download-attachment":
        return _sources_download_attachment(args)
    if args.command in {"scan", "download", "export", "status-check"}:
        LOGGER.error(
            "%s is intentionally disabled in Phase 0; complete source audit first.",
            args.command,
        )
        return 2

    parser.print_help()
    return 1


def _config_validate() -> int:
    repo = repository_root()
    results = validate_repository_configs(repo)
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"{status} {result.path.relative_to(repo)} - {result.message}")
    return 0 if all(result.ok for result in results) else 1


def _print_schema() -> int:
    repo = repository_root()
    schema_path = repo / "src" / "tender_radar" / "schema.sql"
    sys.stdout.write(schema_path.read_text(encoding="utf-8"))
    return 0


def _db_init(db_path: Path) -> int:
    initialize(db_path)
    _emit_json({"db_path": str(db_path), "initialized": True})
    return 0


def _runtime_scheduled_run(args: argparse.Namespace) -> int:
    from tender_radar.ui_server import run_scheduled_poll_and_alert

    payload = run_scheduled_poll_and_alert(
        scope=args.scope,
        sort=args.sort,
        limit=args.limit,
        ai_batch_size=args.ai_batch_size,
        enrichment_limit=args.enrichment_limit,
        recipient=args.recipient,
        dry_run=args.dry_run,
        report_path=Path(args.report),
        markdown_report_path=Path(args.markdown_report),
    )
    _emit_json(payload)
    return 0 if payload.get("ok") else 1


def _sources_health(allow_insecure_tls: bool = False) -> int:
    health = health_check(allow_insecure_tls=allow_insecure_tls)
    _emit_json(health.__dict__)
    return 0 if health.reachable else 1


def _sources_audit_whitelist(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    report = audit_source_whitelist(
        Path(args.config),
        timeout_seconds=args.timeout,
        allow_insecure_tls=args.allow_insecure_tls,
    )
    write_source_audit_report(report, report_path, markdown_path)
    output = {
        "config_path": args.config,
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path) if markdown_path else None,
        "summary": report.get("summary"),
    }
    _emit_json(output)
    return 0


def _sources_expanded_report(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    report = build_expanded_report(
        sources_config_path=Path(args.config),
        eshidis_candidates_path=Path(args.eshidis_candidates) if args.eshidis_candidates else None,
        kimdis_pages=args.kimdis_pages,
        authority_limit_per_source=args.authority_limit_per_source,
        timeout_seconds=args.timeout,
        allow_insecure_tls=args.allow_insecure_tls,
        as_of=date.fromisoformat(args.as_of_date) if args.as_of_date else None,
        previous_report_path=Path(args.previous_report) if args.previous_report else None,
        kimdis_source_ids=set(args.kimdis_source_id) if args.kimdis_source_id is not None else None,
        authority_source_ids=set(args.authority_source_id) if args.authority_source_id is not None else None,
    )
    write_expanded_report(report, report_path, markdown_path)
    _emit_json(
        {
            "report_path": str(report_path),
            "markdown_report_path": str(markdown_path) if markdown_path else None,
            "summary": report.get("summary"),
        }
    )
    return 0


def _sources_ai_triage_report(args: argparse.Namespace) -> int:
    from tender_radar.ai_triage import build_ai_triage_report, write_ai_triage_report
    from tender_radar.ui_server import dashboard_payload

    dashboard = dashboard_payload(scope=args.scope, sort=args.sort, apply_triage=False)
    rows = dashboard.get("tenders") if isinstance(dashboard.get("tenders"), list) else []
    report = build_ai_triage_report(
        [row for row in rows if isinstance(row, dict)],
        model=args.model,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout,
    )
    report["dashboard_summary"] = dashboard.get("summary") if isinstance(dashboard.get("summary"), dict) else {}
    report_path = Path(args.report)
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    write_ai_triage_report(report, report_path, markdown_path)
    _emit_json(
        {
            "report_path": str(report_path),
            "markdown_report_path": str(markdown_path) if markdown_path else None,
            "dashboard_summary": report.get("dashboard_summary"),
            "summary": report.get("summary"),
        }
    )
    return 1 if report.get("errors") else 0


def _sources_fetch_kimdis_open_proc(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    report = fetch_kimdis_open_proc_candidates(
        expanded_report_path=Path(args.expanded_report),
        download_dir=Path(args.download_dir),
        timeout_seconds=args.timeout,
        allow_insecure_tls=args.allow_insecure_tls,
        limit=args.limit,
        official_id=args.official_id,
        force=args.force,
        sources_config_path=Path(args.config),
        text_dir=Path(args.text_dir),
        retry_count=args.retries,
        retry_delay_seconds=args.retry_delay,
        request_delay_seconds=args.request_delay,
    )
    write_kimdis_fetch_report(report, report_path, markdown_path)
    document_index_path = Path(args.document_index) if args.document_index else None
    document_index = (
        write_kimdis_document_index(report, document_index_path, merge_existing=bool(args.official_id))
        if document_index_path
        else None
    )
    _emit_json(
        {
            "report_path": str(report_path),
            "markdown_report_path": str(markdown_path) if markdown_path else None,
            "document_index_path": str(document_index_path) if document_index_path else None,
            "summary": report.get("summary"),
            "document_index_summary": document_index.get("fetch_report_summary") if document_index else None,
        }
    )
    summary = report.get("summary")
    if isinstance(summary, dict) and summary.get("failed"):
        return 1
    return 0


def _sources_discover_active(args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise ValueError("--limit must be positive.")
    report_path = Path(args.report)
    payload = discover_active_candidates_audit(
        report_path,
        status_value=args.status_value,
        limit=args.limit,
        allow_insecure_tls=args.allow_insecure_tls,
        headful=args.headful,
    )
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_discovery_markdown(payload), encoding="utf-8")
    output = {
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path) if markdown_path else None,
        "candidate_status": payload.get("candidate_status"),
        "candidates_found": len(payload.get("candidates", [])),
        "coverage": payload.get("coverage"),
        "navigation_error": payload.get("navigation_error"),
        "search_attempt": payload.get("search_attempt"),
    }
    _emit_json(output)
    return 1 if payload.get("navigation_error") else 0


def _documents_analyze(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    attachments = list_downloaded_attachments(db_path, args.eshidis_id)
    report_path = Path(args.report or "work/reports/document_analysis.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    text_dir = Path(args.text_dir)
    text_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for attachment in attachments:
        analysis = analyze_document(Path(attachment.local_path), attachment.original_name)
        text_path = _write_text_artifact(text_dir, attachment.eshidis_id, attachment.attachment_id, analysis.full_text)
        summary = upsert_document_analysis(
            db_path,
            attachment.attachment_id,
            analysis.document_type,
            analysis.classification_confidence,
            analysis.extraction_status,
            analysis.page_or_sheet_count,
            analysis.text_sample,
            str(text_path) if text_path else None,
            analysis.extraction_error,
            analysis.ocr_status,
            analysis.ocr_error,
        )
        analysis_dict = analysis.to_dict()
        analysis_dict.pop("full_text", None)
        results.append(
            {
                "document_id": summary.document_id,
                "attachment_id": attachment.attachment_id,
                "eshidis_id": attachment.eshidis_id,
                "original_name": attachment.original_name,
                "local_path": attachment.local_path,
                "size_bytes": attachment.size_bytes,
                "sha256": attachment.sha256,
                "text_path": str(text_path) if text_path else None,
                **analysis_dict,
            }
        )
    output = {
        "db_path": str(db_path),
        "report_path": str(report_path),
        "markdown_report_path": args.markdown_report,
        "eshidis_id": args.eshidis_id,
        "documents_analyzed": len(results),
        "documents": results,
    }
    report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_report:
        markdown_path = Path(args.markdown_report)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown_report(output), encoding="utf-8")
    _emit_json(output)
    return 0


def _write_text_artifact(text_dir: Path, eshidis_id: str, attachment_id: int, full_text: str | None) -> Path | None:
    if not full_text:
        return None
    safe_eshidis_id = "".join(ch if ch.isalnum() else "_" for ch in eshidis_id)
    path = text_dir / f"{safe_eshidis_id}_{attachment_id}.txt"
    path.write_text(full_text, encoding="utf-8")
    return path


def _search_run(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    profile_path = Path(args.profile)
    profile = load_search_profile(profile_path)
    search_run_id = create_search_run(db_path, profile.profile_id, profile_path)
    documents = list_searchable_documents(
        db_path,
        eshidis_id=args.eshidis_id,
        document_types=profile.include_document_types,
    )
    matches = match_profile(profile, documents)
    hit_ids = []
    for match in matches:
        hit_ids.append(
            insert_search_hit(
                db_path,
                search_run_id=search_run_id,
                tender_id=match.tender_id,
                document_id=match.document_id,
                match_type=match.match_type,
                confidence=match.confidence,
                matched_text=match.context,
                provenance={
                    "profile_id": profile.profile_id,
                    "term": match.term,
                    "document_type": match.document_type,
                    "original_name": match.original_name,
                    "local_path": match.local_path,
                },
            )
        )
    report_path = Path(args.report or f"work/reports/search_{profile.profile_id}.json")
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "db_path": str(db_path),
        "search_run_id": search_run_id,
        "profile_id": profile.profile_id,
        "profile_name": profile.name,
        "eshidis_id": args.eshidis_id,
        "documents_scanned": len(documents),
        "matches_found": len(matches),
        "hit_ids": hit_ids,
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path) if markdown_path else None,
        "matches": [match.to_dict() for match in matches],
    }
    report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.write_text(render_search_markdown(profile, matches), encoding="utf-8")
    finish_search_run(
        db_path,
        search_run_id,
        "COMPLETED",
        {
            "documents_scanned": len(documents),
            "matches_found": len(matches),
            "report_path": str(report_path),
            "markdown_report_path": str(markdown_path) if markdown_path else None,
        },
    )
    _emit_json(output)
    return 0


def _evaluate_run(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    profile_path = Path(args.profile)
    profile = load_evaluation_profile(profile_path)
    documents = list_searchable_documents(db_path, eshidis_id=args.eshidis_id)
    evaluations = evaluate_documents(profile, documents)
    report_path = Path(args.report or f"work/reports/evaluation_{profile.profile_id}.json")
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "db_path": str(db_path),
        "profile_id": profile.profile_id,
        "profile_name": profile.name,
        "profile_path": str(profile_path),
        "eshidis_id": args.eshidis_id,
        "documents_scanned": len(documents),
        "tenders_matched": len(evaluations),
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path) if markdown_path else None,
        "evaluations": [item.to_dict() for item in evaluations],
    }
    report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.write_text(render_evaluation_markdown(profile, evaluations), encoding="utf-8")
    _emit_json(output)
    return 0


def _status_verify(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    report_path = Path(args.report or f"work/reports/status_verification_{args.eshidis_id}.json")
    markdown_path = Path(args.markdown_report) if args.markdown_report else None
    result = verify_tender_status(db_path, args.eshidis_id)
    write_status_reports(result, report_path, markdown_path)
    output = {
        "db_path": str(db_path),
        "eshidis_id": args.eshidis_id,
        "recommended_status": result.recommended_status,
        "status_confidence": result.status_confidence,
        "verified_active": result.verified_active,
        "signals_found": len(result.signals),
        "documents_checked": result.documents_checked,
        "latest_attachments_checked": result.latest_attachments_checked,
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path) if markdown_path else None,
    }
    _emit_json(output)
    return 0


def _entalmata_scan(args: argparse.Namespace) -> int:
    from tender_radar.entalmata import scan_entalmata

    report = scan_entalmata(
        db_path=Path(args.db),
        config_path=Path(args.config),
        download_dir=Path(args.download_dir),
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit_json({"report_path": str(report_path), "summary": report.get("summary"), "errors": report.get("errors")})
    return 0 if report.get("ok") else 1


def _sources_import_resource_audit(audit_json: Path, db_path: Path) -> int:
    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    summary = _import_resource_payload(payload, audit_json, db_path)
    _emit_json(
        {
            "db_path": str(summary.db_path),
            "tender_id": summary.tender_id,
            "eshidis_id": summary.eshidis_id,
            "attachments_imported": summary.attachments_imported,
        }
    )
    return 0


def _import_resource_payload(payload: dict[str, object], audit_json: Path, db_path: Path):
    details = parse_eshidis_resource_text(payload["target_url"], payload["snapshot"]["bodyTextSample"])
    attachment_body = _find_attachment_body(payload)
    attachments = (
        parse_eshidis_attachment_xml(attachment_body)
        if attachment_body is not None
        else EshidisAttachmentListing(row_count=None, filenames=())
    )
    return import_eshidis_resource(db_path, details, attachments, raw_path=audit_json)


def _sources_fetch_resource(args: argparse.Namespace) -> int:
    audit_path = Path(args.out or f"work/source_audit/eshidis_resource_audit_{args.eshidis_id}.json")
    payload = fetch_resource_audit(
        args.eshidis_id,
        audit_path,
        allow_insecure_tls=args.allow_insecure_tls,
        headful=args.headful,
    )
    output: dict[str, object] = {
        "audit_json": str(audit_path),
        "eshidis_id": args.eshidis_id,
        "navigation_error": payload.get("navigation_error"),
    }
    if not args.no_import:
        summary = _import_resource_payload(payload, audit_path, Path(args.db))
        output.update(
            {
                "db_path": str(summary.db_path),
                "tender_id": summary.tender_id,
                "attachments_imported": summary.attachments_imported,
            }
        )
    _emit_json(output)
    return 0


def _sources_download_attachment(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    attachments = list_latest_attachments(db_path, args.eshidis_id)
    row_indexes = _download_row_indexes(args, attachments)
    if len(row_indexes) > args.limit:
        raise ValueError(f"Refusing to download {len(row_indexes)} rows; increase --limit if intentional.")
    if args.out and len(row_indexes) > 1:
        raise ValueError("--out can only be used with a single row download.")

    results = []
    failures = 0
    for row_index in row_indexes:
        status = attachments[row_index] if row_index < len(attachments) else None
        if status and _should_skip_download(status, force=args.force):
            results.append(
                {
                    "row_index": row_index,
                    "status": "skipped",
                    "reason": "already_downloaded",
                    "attachment_id": status.attachment_id,
                    "original_name": status.original_name,
                    "local_path": status.local_path,
                    "size_bytes": status.size_bytes,
                    "sha256": status.sha256,
                }
            )
            continue
        audit_path = Path(args.out or f"work/source_audit/eshidis_download_audit_{args.eshidis_id}_{row_index}.json")
        payload = download_attachment_audit(
            args.eshidis_id,
            row_index,
            audit_path,
            Path(args.download_dir),
            allow_insecure_tls=args.allow_insecure_tls,
            headful=args.headful,
        )
        downloaded = payload.get("downloaded_file")
        result: dict[str, object] = {
            "row_index": row_index,
            "status": "downloaded" if downloaded else "failed",
            "audit_json": str(audit_path),
            "download_error": payload.get("download_error"),
            "downloaded_file": downloaded,
        }
        if not downloaded:
            failures += 1
            results.append(result)
            continue
        if not args.no_import:
            summary = _import_download_payload(payload, db_path)
            result.update(
                {
                    "db_path": str(summary.db_path),
                    "attachment_id": summary.attachment_id,
                    "original_name": summary.original_name,
                    "local_path": summary.local_path,
                    "size_bytes": summary.size_bytes,
                    "sha256": summary.sha256,
                }
            )
        results.append(result)

    output = {
        "eshidis_id": args.eshidis_id,
        "requested_rows": row_indexes,
        "downloaded": sum(1 for result in results if result["status"] == "downloaded"),
        "skipped": sum(1 for result in results if result["status"] == "skipped"),
        "failed": failures,
        "results": results,
    }
    _emit_json(output)
    return 1 if failures else 0


def _download_row_indexes(args: argparse.Namespace, attachments: list[AttachmentStatus]) -> list[int]:
    if args.all:
        indexes = list(range(len(attachments)))
    elif args.row_indexes:
        indexes = _parse_row_indexes(args.row_indexes)
    else:
        indexes = [args.row_index]
    if not indexes:
        raise ValueError("No attachment rows selected.")
    if any(index < 0 for index in indexes):
        raise ValueError("Attachment row indexes must be zero or positive.")
    if attachments:
        max_index = len(attachments) - 1
        invalid = [index for index in indexes if index > max_index]
        if invalid:
            raise ValueError(f"Attachment row index out of range: {invalid}; latest row count is {len(attachments)}.")
    return indexes


def _parse_row_indexes(value: str) -> list[int]:
    indexes: list[int] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        indexes.append(int(item))
    return list(dict.fromkeys(indexes))


def _should_skip_download(status: AttachmentStatus, *, force: bool) -> bool:
    if force or not status.local_path or not status.sha256:
        return False
    return Path(status.local_path).exists()


def _sources_import_download_audit(download_audit_json: Path, db_path: Path) -> int:
    payload = json.loads(download_audit_json.read_text(encoding="utf-8"))
    summary = _import_download_payload(payload, db_path)
    _emit_json(
        {
            "db_path": str(summary.db_path),
            "attachment_id": summary.attachment_id,
            "original_name": summary.original_name,
            "local_path": summary.local_path,
            "size_bytes": summary.size_bytes,
            "sha256": summary.sha256,
        }
    )
    return 0


def _import_download_payload(payload: dict[str, object], db_path: Path):
    downloaded = payload.get("downloaded_file")
    if not isinstance(downloaded, dict):
        raise ValueError("Download audit JSON has no downloaded_file object.")
    original_name = downloaded.get("name")
    local_path = downloaded.get("path")
    size_bytes = downloaded.get("size_bytes")
    sha256 = downloaded.get("sha256")
    eshidis_id = payload.get("eshidis_id")
    if not all((original_name, local_path, size_bytes, sha256, eshidis_id)):
        raise ValueError("Download audit JSON is missing required metadata.")
    return import_attachment_download(
        db_path,
        str(eshidis_id),
        str(original_name),
        str(local_path),
        int(size_bytes),
        str(sha256),
    )


def _find_attachment_body(payload: dict[str, object]) -> str | None:
    response_bodies = payload.get("response_bodies")
    if not isinstance(response_bodies, list):
        raise ValueError("Audit JSON has no response_bodies list.")
    for item in response_bodies:
        if not isinstance(item, dict):
            continue
        sample = item.get("body_sample")
        if isinstance(sample, str) and '_rowCount="' in sample and "t1:" in sample:
            return sample
    return None


def _emit_json(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
