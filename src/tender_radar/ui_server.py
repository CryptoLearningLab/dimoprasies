from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import io
import json
import mimetypes
import re
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, unquote, urlparse
from urllib.request import Request, urlopen

from tender_radar.config import load_config
from tender_radar.discovery_watermark import (
    append_discovery_run,
    build_discovery_run_record,
    latest_discovery_run,
    latest_successful_discovery_run,
    utc_now_iso,
)
from tender_radar.evaluation import normalize_evaluation_config, save_evaluation_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_ESHIDIS_DISCOVERY_LIMIT = 100
DEFAULT_KIMDIS_DISCOVERY_PAGES = 20
DEFAULT_AUTHORITY_LIMIT_PER_SOURCE = 10
MAX_BACKFILL_ESHIDIS_LIMIT = 500
MAX_BACKFILL_KIMDIS_PAGES = 80
COMMAND_LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Tender Radar UI server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="Open the UI in the default browser.")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), TenderRadarHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Tender Radar UI running at {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Tender Radar UI.")
    finally:
        server.server_close()
    return 0


class TenderRadarHandler(BaseHTTPRequestHandler):
    server_version = "TenderRadarUI/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
            return
        if parsed.path == "/styles.css":
            self._send_text(STYLES_CSS, "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_text(APP_JS, "application/javascript; charset=utf-8")
            return
        if parsed.path == "/api/status":
            self._send_json(status_payload())
            return
        if parsed.path == "/api/candidates":
            self._send_json(candidates_payload())
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = job_payload(job_id)
            if not job:
                self._send_json({"ok": False, "error": "Unknown job id."}, status=404)
                return
            self._send_json(job)
            return
        if parsed.path == "/api/dashboard":
            query = parse_qs(parsed.query)
            scope = query.get("scope", ["focus"])[0]
            sort = query.get("sort", ["deadline_asc"])[0]
            self._send_json(dashboard_payload(scope=scope, sort=sort))
            return
        if parsed.path == "/api/document-preview":
            query = parse_qs(parsed.query)
            eshidis_id = require_eshidis_id({"eshidis_id": query.get("eshidis_id", [""])[0]})
            self._send_json(document_preview_payload(eshidis_id))
            return
        if parsed.path == "/api/kimdis-document-preview":
            query = parse_qs(parsed.query)
            official_id = require_kimdis_id({"official_id": query.get("official_id", [""])[0]})
            self._send_json(kimdis_document_preview_payload(official_id))
            return
        if parsed.path == "/api/authority-document-preview":
            query = parse_qs(parsed.query)
            row_key = require_authority_document_key({"row_key": query.get("row_key", [""])[0]})
            self._send_json(authority_document_preview_payload(row_key))
            return
        if parsed.path == "/api/document-file":
            query = parse_qs(parsed.query)
            attachment_id = int(query.get("attachment_id", ["0"])[0])
            path = local_attachment_path(attachment_id)
            if not path:
                self._send_json({"error": "Attachment file is not available."}, status=404)
                return
            self._send_file(path)
            return
        if parsed.path == "/api/kimdis-document-file":
            query = parse_qs(parsed.query)
            official_id = require_kimdis_id({"official_id": query.get("official_id", [""])[0]})
            path = kimdis_document_file_path(official_id)
            if not path:
                self._send_json({"error": "KIMDIS document file is not available."}, status=404)
                return
            self._send_file(path)
            return
        if parsed.path == "/api/authority-document-file":
            query = parse_qs(parsed.query)
            row_key = require_authority_document_key({"row_key": query.get("row_key", [""])[0]})
            index = int(query.get("index", ["0"])[0])
            path = authority_document_file_path(row_key, index)
            if not path:
                self._send_json({"error": "Authority document file is not available."}, status=404)
                return
            self._send_file(path)
            return
        if parsed.path == "/api/document-zip":
            query = parse_qs(parsed.query)
            identifier = require_document_zip_identifier({"identifier": query.get("identifier", [""])[0]})
            archive_name, archive_body = document_zip_bytes(identifier)
            if not archive_body:
                self._send_json({"error": "No downloaded documents are available for this tender."}, status=404)
                return
            self._send_bytes(
                archive_body,
                "application/zip",
                extra_headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
            )
            return
        if parsed.path == "/api/evaluation-profile":
            query = parse_qs(parsed.query)
            profile_path = safe_evaluation_profile_path(query.get("path", [""])[0])
            self._send_json(evaluation_profile_payload(profile_path))
            return
        if parsed.path == "/api/report":
            query = parse_qs(parsed.query)
            path = report_path(query.get("path", [""])[0])
            if not path:
                self._send_json({"error": "Unknown report path."}, status=404)
                return
            self._send_file(path)
            return
        self._send_json({"error": "Not found."}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/discover":
                limit = int(payload.get("limit") or DEFAULT_ESHIDIS_DISCOVERY_LIMIT)
                backfill = bool(payload.get("backfill"))
                self._send_json(start_job("discover", run_discovery_search, limit=limit, backfill=backfill), status=202)
                return
            if parsed.path == "/api/fetch-resource":
                eshidis_id = require_eshidis_id(payload)
                self._send_json(
                    start_job(
                        "fetch-resource",
                        run_cli_command,
                        ["sources", "fetch-resource", eshidis_id, "--allow-insecure-tls"],
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/download-all":
                eshidis_id = require_eshidis_id(payload)
                self._send_json(
                    start_job(
                        "download-all",
                        run_cli_command,
                        ["sources", "download-attachment", eshidis_id, "--all", "--limit", "50", "--allow-insecure-tls"],
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/fetch-selected":
                identifier = require_fetch_identifier(payload)
                self._send_json(start_job("fetch-selected", run_selected_fetch, identifier), status=202)
                return
            if parsed.path == "/api/dismiss-tender":
                row_key = require_row_key(payload)
                self._send_json(dismiss_tender(row_key))
                return
            if parsed.path == "/api/fetch-kimdis-open-proc":
                official_id = str(payload.get("official_id") or "").strip() or None
                self._send_json(start_job("fetch-kimdis-open-proc", run_kimdis_fetch, official_id=official_id), status=202)
                return
            if parsed.path == "/api/analyze":
                eshidis_id = require_eshidis_id(payload)
                self._send_json(
                    start_job(
                        "analyze",
                        run_cli_command,
                        [
                            "documents",
                            "analyze",
                            "--eshidis-id",
                            eshidis_id,
                            "--report",
                            f"work/reports/document_analysis_{eshidis_id}.json",
                            "--markdown-report",
                            f"work/reports/document_analysis_{eshidis_id}.md",
                        ]
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/search":
                eshidis_id = require_eshidis_id(payload)
                profile = str(payload.get("profile") or "config/search_profiles/road_maintenance.yml")
                profile_id = Path(profile).stem
                self._send_json(
                    start_job(
                        "search",
                        run_cli_command,
                        [
                            "search",
                            "run",
                            "--profile",
                            profile,
                            "--eshidis-id",
                            eshidis_id,
                            "--report",
                            f"work/reports/search_{profile_id}_{eshidis_id}.json",
                            "--markdown-report",
                            f"work/reports/search_{profile_id}_{eshidis_id}.md",
                        ]
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/evaluate":
                eshidis_id = require_eshidis_id(payload)
                profile = str(payload.get("profile") or "config/evaluation_profiles/public_works_dynamic.yml")
                profile_id = Path(profile).stem
                self._send_json(
                    start_job(
                        "evaluate",
                        run_cli_command,
                        [
                            "evaluate",
                            "run",
                            "--profile",
                            profile,
                            "--eshidis-id",
                            eshidis_id,
                            "--report",
                            f"work/reports/evaluation_{profile_id}_{eshidis_id}.json",
                            "--markdown-report",
                            f"work/reports/evaluation_{profile_id}_{eshidis_id}.md",
                        ]
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/evaluation-profile":
                profile_path = safe_evaluation_profile_path(str(payload.get("path") or ""))
                data = payload.get("data")
                if not isinstance(data, dict):
                    raise ValueError("Evaluation profile payload must contain a data object.")
                saved = save_evaluation_config(profile_path, data)
                self._send_json({"ok": True, "path": str(profile_path.relative_to(REPO_ROOT)), "data": saved})
                return
            self._send_json({"error": "Not found."}, status=404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        self._send_text(html, "text/html; charset=utf-8")

    def _send_text(self, text: str, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        body = path.read_bytes()
        content_type = content_type_for_path(path)
        self._send_bytes(body, content_type)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        *,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def run_cli_command(args: list[str]) -> dict[str, Any]:
    if not COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another command is already running. Wait for it to finish."}
    try:
        result = run_cli_process(args, timeout=180)
        result["candidates"] = candidates_payload()
        return result
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": f"Command timed out: {exc!r}", "command": " ".join(args)}
    finally:
        COMMAND_LOCK.release()


def start_job(name: str, target: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    now = time.time()
    with JOBS_LOCK:
        prune_jobs(now=now)
        JOBS[job_id] = {
            "ok": True,
            "job_id": job_id,
            "name": name,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
        }
    thread = threading.Thread(target=_run_job, args=(job_id, target, args, kwargs), daemon=True)
    thread.start()
    return {"ok": True, "job_id": job_id, "name": name, "status": "running", "poll_url": f"/api/jobs/{job_id}"}


def _run_job(job_id: str, target: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    try:
        result = target(*args, **kwargs)
        status = "failed" if isinstance(result, dict) and result.get("ok") is False else "completed"
        error = result.get("error") if isinstance(result, dict) else None
    except Exception as exc:  # pragma: no cover - defensive boundary for background jobs
        result = None
        status = "failed"
        error = str(exc)
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update({"status": status, "updated_at": time.time(), "result": result, "error": error})


def job_payload(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        return dict(job)


def prune_jobs(*, now: float, max_age_seconds: int = 3600) -> None:
    expired = [job_id for job_id, job in JOBS.items() if now - float(job.get("updated_at") or 0) > max_age_seconds]
    for job_id in expired:
        JOBS.pop(job_id, None)


def run_selected_fetch(identifier: str) -> dict[str, Any]:
    if authority_row_by_key(identifier):
        return run_authority_fetch(identifier)
    if is_kimdis_identifier(identifier):
        kimdis_result = run_kimdis_fetch(official_id=identifier)
        linked_ids = kimdis_linked_eshidis_ids(identifier)
        if not linked_ids:
            return {
                "ok": kimdis_result.get("ok") is not False,
                "kimdis_fetch": kimdis_result,
                "linked_eshidis_ids": [],
                "eshidis_fetch": None,
                "dashboard": dashboard_payload(scope="focus"),
            }
        steps: list[dict[str, Any]] = []
        for eshidis_id in linked_ids:
            steps.extend(
                [
                    {
                        "name": f"fetch_detail_{eshidis_id}",
                        "args": ["sources", "fetch-resource", eshidis_id, "--allow-insecure-tls"],
                        "timeout": 180,
                    },
                    {
                        "name": f"download_files_{eshidis_id}",
                        "args": [
                            "sources",
                            "download-attachment",
                            eshidis_id,
                            "--all",
                            "--limit",
                            "50",
                            "--allow-insecure-tls",
                        ],
                        "timeout": 180,
                    },
                ]
            )
        eshidis_result = run_cli_steps(steps, dashboard_scope="focus")
        return {
            "ok": kimdis_result.get("ok") is not False and eshidis_result.get("ok") is not False,
            "kimdis_fetch": kimdis_result,
            "linked_eshidis_ids": linked_ids,
            "eshidis_fetch": eshidis_result,
            "dashboard": eshidis_result.get("dashboard") or dashboard_payload(scope="focus"),
        }
    eshidis_id = require_eshidis_id({"eshidis_id": identifier})
    steps = [
        {"name": "fetch_detail", "args": ["sources", "fetch-resource", eshidis_id, "--allow-insecure-tls"], "timeout": 180},
        {
            "name": "download_files",
            "args": ["sources", "download-attachment", eshidis_id, "--all", "--limit", "50", "--allow-insecure-tls"],
            "timeout": 180,
        },
    ]
    return run_cli_steps(steps, dashboard_scope="focus")


def run_authority_fetch(row_key: str) -> dict[str, Any]:
    row = authority_row_by_key(row_key)
    if not row:
        return {"ok": False, "error": "Authority row is not present in the current expanded report."}
    urls = [str(url) for url in row.get("attachment_urls") or [] if str(url).strip()]
    if not urls and row.get("attachment_url"):
        urls = [str(row.get("attachment_url"))]
    if not urls:
        return {"ok": False, "error": "No authority attachment URLs are known for this row."}
    target_dir = authority_download_dir(row_key)
    target_dir.mkdir(parents=True, exist_ok=True)
    documents = []
    failures = []
    for index, url in enumerate(urls):
        try:
            path, size_bytes = download_authority_document(url, target_dir, index)
            documents.append(
                {
                    "row_key": row_key,
                    "official_id": row.get("official_id"),
                    "title": row.get("title"),
                    "source_url": row.get("official_url"),
                    "attachment_url": url,
                    "local_path": str(path),
                    "original_filename": path.name,
                    "size_bytes": size_bytes,
                    "retrieved_at": utc_now_iso(),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive network boundary
            failures.append({"url": url, "message": str(exc)})
    index_payload = write_authority_document_index(row_key, documents)
    return {
        "ok": not failures and bool(documents),
        "row_key": row_key,
        "downloaded": len(documents),
        "failed": len(failures),
        "failures": failures,
        "document_index": index_payload,
        "dashboard": dashboard_payload(scope="focus"),
    }


def run_kimdis_fetch(*, official_id: str | None = None) -> dict[str, Any]:
    args = kimdis_fetch_args()
    if official_id:
        official_id = require_kimdis_id({"official_id": official_id})
        args.extend(["--official-id", official_id])
    return run_cli_command(args)


def kimdis_fetch_args() -> list[str]:
    return [
        "sources",
        "fetch-kimdis-open-proc",
        "--expanded-report",
        "work/reports/expanded_discovery_report.json",
        "--config",
        "config/sources.yml",
        "--download-dir",
        "work/download_audit/kimdis",
        "--text-dir",
        "work/extracted_text/kimdis",
        "--document-index",
        "work/derived/kimdis_open_proc_documents.json",
        "--report",
        "work/reports/kimdis_open_proc_fetch_report.json",
        "--markdown-report",
        "work/reports/kimdis_open_proc_fetch_report.md",
        "--limit",
        "50",
        "--timeout",
        "30",
        "--allow-insecure-tls",
    ]


def run_cli_steps(steps: list[dict[str, Any]], *, dashboard_scope: str | None = None) -> dict[str, Any]:
    if not COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another command is already running. Wait for it to finish."}
    results: list[dict[str, Any]] = []
    try:
        for step in steps:
            result = run_cli_process(step["args"], timeout=int(step.get("timeout") or 180))
            result["name"] = step.get("name")
            results.append(result)
            if result.get("returncode") != 0:
                break
        ok = bool(results) and all(item.get("returncode") == 0 for item in results)
        payload: dict[str, Any] = {
            "ok": ok,
            "command": " && ".join(str(item.get("command") or "") for item in results),
            "steps": results,
            "warnings": [item for item in results if item.get("returncode") not in (0, None)],
            "candidates": candidates_payload(),
        }
        if dashboard_scope:
            payload["dashboard"] = dashboard_payload(scope=dashboard_scope)
        return payload
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": f"Command timed out: {exc!r}", "steps": results}
    finally:
        COMMAND_LOCK.release()


def run_discovery_search(*, limit: int, backfill: bool = False) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("Search limit must be positive.")
    if not COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another command is already running. Wait for it to finish."}
    results: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    preflight: dict[str, Any] | None = None
    try:
        if not backfill:
            preflight = discovery_change_preflight()
            if preflight.get("skip"):
                return {
                    "ok": True,
                    "skipped": True,
                    "skip_reason": "SKIPPED_UNCHANGED",
                    "source_preflight": preflight,
                    "steps": [],
                    "warnings": [],
                    "candidates": candidates_payload(),
                    "expanded_report": expanded_report_payload(),
                    "discovery_runs": [],
                    "discovery_run": latest_discovery_run(discovery_history_path()),
                    "dashboard": dashboard_payload(scope="focus"),
                }
        mode = "backfill" if backfill else "bounded"
        current_limit = limit
        current_kimdis_pages = DEFAULT_KIMDIS_DISCOVERY_PAGES
        previous_success = latest_successful_discovery_run(discovery_history_path())
        while True:
            started_at = utc_now_iso()
            pass_results = []
            steps = discovery_search_steps(
                limit=current_limit,
                as_of_date=date.today().isoformat(),
                kimdis_pages=current_kimdis_pages,
                source_preflight=preflight,
                selective=not backfill,
            )
            for step in steps:
                result = run_cli_process(step["args"], timeout=int(step["timeout"]))
                result["name"] = step["name"]
                pass_results.append(result)
                results.append(result)
            completed_at = utc_now_iso()
            expanded_result = next((item for item in pass_results if item.get("name") == "expanded_report"), {})
            warnings = [
                item
                for item in pass_results
                if item.get("returncode") not in (0, None) or command_summary_errors(item) > 0
            ]
            record = record_discovery_pass(
                started_at=started_at,
                completed_at=completed_at,
                mode=mode,
                eshidis_limit=current_limit,
                kimdis_pages=current_kimdis_pages,
                command_results=pass_results,
                previous_success=previous_success,
            )
            records.append(record)
            pass_ok = expanded_result.get("returncode") == 0 and not warnings and record.get("success") is True
            if not backfill:
                if pass_ok and preflight and preflight.get("current", {}).get("ok"):
                    save_source_fingerprint(preflight["current"])
                return discovery_response(results, warnings, pass_ok, records)
            if record.get("watermark", {}).get("complete"):
                if pass_ok and preflight and preflight.get("current", {}).get("ok"):
                    save_source_fingerprint(preflight["current"])
                return discovery_response(results, warnings, pass_ok, records)
            if current_limit >= MAX_BACKFILL_ESHIDIS_LIMIT and current_kimdis_pages >= MAX_BACKFILL_KIMDIS_PAGES:
                return discovery_response(results, warnings, False, records)
            current_limit = min(MAX_BACKFILL_ESHIDIS_LIMIT, max(current_limit + 1, current_limit * 2))
            current_kimdis_pages = min(MAX_BACKFILL_KIMDIS_PAGES, max(current_kimdis_pages + 1, current_kimdis_pages * 2))
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": f"Command timed out: {exc!r}", "steps": results, "discovery_runs": records}
    finally:
        COMMAND_LOCK.release()


def source_fingerprint_path() -> Path:
    return REPO_ROOT / "work/derived/source_fingerprints.json"


def discovery_change_preflight() -> dict[str, Any]:
    current = quick_source_fingerprint(timeout_seconds=8)
    previous = latest_source_fingerprint()
    reports_exist = (REPO_ROOT / "work/reports/expanded_discovery_report.json").exists()
    exact_skip = bool(
        reports_exist
        and current.get("ok")
        and previous
        and previous.get("hash")
        and previous.get("hash") == current.get("hash")
    )
    partial_skip = bool(
        reports_exist
        and current.get("errors")
        and previous
        and _successful_sources_unchanged(current=current, previous=previous)
    )
    skip = exact_skip or partial_skip
    status = "CHANGED_OR_NO_BASELINE"
    if exact_skip:
        status = "SKIPPED_UNCHANGED"
    elif partial_skip:
        status = "SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS"
    return {
        "ok": current.get("ok"),
        "skip": skip,
        "status": status,
        "changed_source_ids": _changed_source_ids(current=current, previous=previous),
        "current": current,
        "previous_hash": previous.get("hash") if previous else None,
        "current_hash": current.get("hash"),
        "errors": current.get("errors") or [],
    }


def latest_source_fingerprint() -> dict[str, Any] | None:
    path = source_fingerprint_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("latest_complete"), dict):
        return payload["latest_complete"]
    return payload.get("latest") if isinstance(payload.get("latest"), dict) else None


def save_source_fingerprint(fingerprint: dict[str, Any]) -> None:
    path = source_fingerprint_path()
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            existing = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    payload = {"version": 1, "latest": fingerprint}
    if fingerprint.get("ok"):
        payload["latest_complete"] = fingerprint
    elif isinstance(existing.get("latest_complete"), dict):
        payload["latest_complete"] = existing["latest_complete"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _successful_sources_unchanged(*, current: dict[str, Any], previous: dict[str, Any]) -> bool:
    previous_sources = {
        str(item.get("source_id") or ""): _source_fingerprint_signature(item)
        for item in previous.get("sources") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    current_sources = [
        item for item in current.get("sources") or [] if isinstance(item, dict) and item.get("source_id")
    ]
    current_by_id = {str(item.get("source_id") or ""): item for item in current_sources}
    overlap = sorted(set(previous_sources) & set(current_by_id))
    if not previous_sources or len(overlap) < max(1, int(len(previous_sources) * 0.75)):
        return False
    return all(
        previous_sources[source_id] == _source_fingerprint_signature(current_by_id[source_id])
        for source_id in overlap
    )


def _source_fingerprint_signature(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter": source.get("adapter"),
        "token": source.get("token"),
        "date": source.get("date"),
        "count_hint": source.get("count_hint"),
    }


def _changed_source_ids(*, current: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    if not previous:
        return []
    previous_sources = {
        str(item.get("source_id") or ""): _source_fingerprint_signature(item)
        for item in previous.get("sources") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    changed: list[str] = []
    for item in current.get("sources") or []:
        if not isinstance(item, dict) or not item.get("source_id"):
            continue
        source_id = str(item.get("source_id") or "")
        if previous_sources.get(source_id) != _source_fingerprint_signature(item):
            changed.append(source_id)
    return sorted(changed)


def quick_source_fingerprint(*, timeout_seconds: int = 8) -> dict[str, Any]:
    config_path = REPO_ROOT / "config/sources.yml"
    config = load_config(config_path) if config_path.exists() else {}
    sources: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    tasks = [("khmdhs_notice", lambda: _kimdis_notice_fingerprint(timeout_seconds=timeout_seconds))]
    for source in config.get("authority_adapters") or []:
        if not isinstance(source, dict):
            continue
        tasks.append(
            (
                str(source.get("id") or "unknown"),
                lambda source=source: _authority_source_fingerprint(source, timeout_seconds=timeout_seconds),
            )
        )
    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as executor:
        future_sources = {executor.submit(task): source_id for source_id, task in tasks}
        for future in as_completed(future_sources):
            source_id = future_sources[future]
            try:
                sources.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive network boundary
                errors.append({"source": source_id, "message": str(exc)})
    stable_sources = sorted(sources, key=lambda item: str(item.get("source_id") or ""))
    digest = hashlib.sha256(json.dumps(stable_sources, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "ok": not errors,
        "computed_at": utc_now_iso(),
        "hash": digest,
        "sources": stable_sources,
        "errors": errors,
        "status_note": "Cheap source fingerprint; unchanged means expensive discovery can reuse cached reports.",
    }


def _kimdis_notice_fingerprint(*, timeout_seconds: int) -> dict[str, Any]:
    url = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice?page=0"
    request = Request(
        url,
        data=json.dumps({"contractType": "10"}).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "TenderRadar/0.1 source-preflight"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    content = payload.get("content") if isinstance(payload.get("content"), list) else []
    first = content[0] if content and isinstance(content[0], dict) else {}
    return {
        "source_id": "khmdhs_notice",
        "adapter": "api_post",
        "token": first.get("referenceNumber"),
        "date": first.get("submissionDate") or first.get("finalSubmissionDate"),
        "count_hint": len(content),
    }


def _authority_source_fingerprint(source: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    adapter = str(source.get("adapter") or "")
    source_id = str(source.get("id") or "")
    if adapter in {"wordpress_category", "wordpress_page_table", "diavgeia_api"}:
        return _json_source_fingerprint(source, timeout_seconds=timeout_seconds)
    if adapter == "ted_api":
        return _ted_source_fingerprint(source, timeout_seconds=timeout_seconds)
    return _html_source_fingerprint(source, timeout_seconds=timeout_seconds)


def _json_source_fingerprint(source: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    params = dict(source.get("query_params") or {})
    if str(source.get("adapter") or "") == "diavgeia_api":
        params["size"] = 1
        params["page"] = 0
    elif "per_page" in params:
        params["per_page"] = 1
        params["page"] = 1
    url = _url_with_params(str(source.get("url") or ""), params)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "TenderRadar/0.1 source-preflight"})
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    first = _first_json_item(payload)
    return {
        "source_id": source.get("id"),
        "adapter": source.get("adapter"),
        "url": url,
        "token": first.get("id") or first.get("ada") or first.get("decisionId") or first.get("link"),
        "date": first.get("modified") or first.get("date") or first.get("submissionTimestamp") or first.get("issueDate"),
    }


def _ted_source_fingerprint(source: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    body = dict(source.get("body") or {})
    body["limit"] = 1
    body["page"] = 1
    request = Request(
        str(source.get("url") or ""),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "TenderRadar/0.1 source-preflight"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    first = _first_json_item(payload)
    return {
        "source_id": source.get("id"),
        "adapter": source.get("adapter"),
        "token": first.get("publication-number") or first.get("notice-id") or first.get("id"),
        "date": first.get("publication-date"),
    }


def _html_source_fingerprint(source: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    url = str(source.get("url") or "")
    request = Request(url, headers={"Accept": "text/html", "User-Agent": "TenderRadar/0.1 source-preflight"})
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read(300_000)
        headers = response.headers
    text = body.decode("utf-8", errors="replace")
    token = headers.get("ETag") or headers.get("Last-Modified") or _html_listing_token(text)
    return {
        "source_id": source.get("id"),
        "adapter": source.get("adapter"),
        "url": url,
        "token": token,
    }


def _html_listing_token(text: str) -> str:
    anchors: list[dict[str, str]] = []
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, flags=re.IGNORECASE | re.DOTALL):
        href = unquote(match.group(1)).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if re.search(r"(facebook|twitter|instagram|youtube|linkedin|wp-content/themes|wp-json)", href, flags=re.IGNORECASE):
            continue
        label = re.sub(r"<[^>]+>", " ", match.group(2))
        label = re.sub(r"\s+", " ", label).strip()
        haystack = f"{href} {label}"
        if not re.search(
            r"(pdf|zip|docx?|xlsx?|prokir|diagon|tender|διαγωνισ|διακηρ|προκηρ|πρόσκλη|προσκλη|αποφασ|απόφασ)",
            haystack,
            flags=re.IGNORECASE,
        ):
            continue
        anchors.append({"href": href, "label": label[:160]})
        if len(anchors) >= 8:
            break
    if anchors:
        return hashlib.sha256(json.dumps(anchors, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    compact = re.sub(r"\s+", " ", re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL))
    return hashlib.sha256(compact[:20_000].encode("utf-8", errors="replace")).hexdigest()


def _first_json_item(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    if not isinstance(payload, dict):
        return {}
    for key in ("content", "decisions", "notices"):
        value = payload.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return payload


def _url_with_params(url: str, params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    if not clean:
        return url
    return f"{url}{'&' if '?' in url else '?'}{urlencode(clean)}"


def discovery_response(
    results: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    ok: bool,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": ok,
        "command": " && ".join(item["command"] for item in results),
        "steps": results,
        "warnings": warnings,
        "candidates": candidates_payload(),
        "expanded_report": expanded_report_payload(),
        "discovery_runs": records,
        "discovery_run": records[-1] if records else None,
        "dashboard": dashboard_payload(scope="focus"),
    }


def record_discovery_pass(
    *,
    started_at: str,
    completed_at: str,
    mode: str,
    eshidis_limit: int,
    kimdis_pages: int,
    command_results: list[dict[str, Any]],
    previous_success: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history_path = discovery_history_path()
    if previous_success is None:
        previous_success = latest_successful_discovery_run(history_path)
    record = build_discovery_run_record(
        started_at=started_at,
        completed_at=completed_at,
        mode=mode,
        eshidis_limit=eshidis_limit,
        kimdis_pages=kimdis_pages,
        command_results=command_results,
        eshidis_report_path=REPO_ROOT / "work/reports/eshidis_active_candidates.json",
        expanded_report_path=REPO_ROOT / "work/reports/expanded_discovery_report.json",
        previous_success=previous_success,
        max_eshidis_limit=MAX_BACKFILL_ESHIDIS_LIMIT,
        max_kimdis_pages=MAX_BACKFILL_KIMDIS_PAGES,
    )
    append_discovery_run(history_path, record)
    return record


def discovery_search_steps(
    *,
    limit: int,
    as_of_date: str,
    kimdis_pages: int = DEFAULT_KIMDIS_DISCOVERY_PAGES,
    source_preflight: dict[str, Any] | None = None,
    selective: bool = False,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    changed_source_ids = set(source_preflight.get("changed_source_ids") or []) if source_preflight else set()
    has_previous_baseline = bool(source_preflight and source_preflight.get("previous_hash"))
    selective_refresh = selective and has_previous_baseline and bool(changed_source_ids)
    if not selective_refresh:
        steps.append(
            {
                "name": "eshidis_discover",
                "timeout": 180,
                "args": [
                    "sources",
                    "discover-active",
                    "--allow-insecure-tls",
                    "--limit",
                    str(limit),
                    "--report",
                    "work/reports/eshidis_active_candidates.json",
                    "--markdown-report",
                    "work/reports/eshidis_active_candidates.md",
                ],
            }
        )
    expanded_args = [
        "sources",
        "expanded-report",
        "--allow-insecure-tls",
        "--kimdis-pages",
        str(kimdis_pages),
        "--authority-limit-per-source",
        str(DEFAULT_AUTHORITY_LIMIT_PER_SOURCE),
        "--timeout",
        "20",
        "--as-of-date",
        as_of_date,
        "--eshidis-candidates",
        "work/reports/eshidis_active_candidates.json",
        "--report",
        "work/reports/expanded_discovery_report.json",
        "--markdown-report",
        "work/reports/expanded_discovery_report.md",
    ]
    if selective_refresh:
        expanded_args.extend(["--previous-report", "work/reports/expanded_discovery_report.json"])
        kimdis_source_ids = sorted(source_id for source_id in changed_source_ids if source_id == "khmdhs_notice")
        authority_source_ids = sorted(source_id for source_id in changed_source_ids if source_id in authority_source_ids_from_config())
        if not kimdis_source_ids:
            expanded_args.extend(["--kimdis-source-id", "__none__"])
        else:
            for source_id in kimdis_source_ids:
                expanded_args.extend(["--kimdis-source-id", source_id])
        if not authority_source_ids:
            expanded_args.extend(["--authority-source-id", "__none__"])
        else:
            for source_id in authority_source_ids:
                expanded_args.extend(["--authority-source-id", source_id])
    steps.append(
        {
            "name": "expanded_report",
            "timeout": 300,
            "args": expanded_args,
        },
    )
    return steps


def authority_source_ids_from_config() -> set[str]:
    config_path = REPO_ROOT / "config/sources.yml"
    config = load_config(config_path) if config_path.exists() else {}
    return {
        str(source.get("id") or "")
        for source in config.get("authority_adapters") or []
        if isinstance(source, dict) and source.get("id")
    }


def run_cli_process(args: list[str], *, timeout: int) -> dict[str, Any]:
    command = [sys.executable, "-m", "tender_radar", *args]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": " ".join(args),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def command_summary_errors(result: dict[str, Any]) -> int:
    try:
        payload = json.loads(str(result.get("stdout") or "{}"))
    except json.JSONDecodeError:
        return 0
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if not isinstance(summary, dict):
        return 0
    try:
        return int(summary.get("errors") or 0)
    except (TypeError, ValueError):
        return 0


def require_eshidis_id(payload: dict[str, Any]) -> str:
    value = str(payload.get("eshidis_id") or "").strip()
    if not value.isdigit() or len(value) < 5 or len(value) > 7:
        raise ValueError("ESHIDIS id must be a 5-7 digit number.")
    return value


def require_kimdis_id(payload: dict[str, Any]) -> str:
    value = str(payload.get("official_id") or "").strip()
    if not re.fullmatch(r"\d{2}PROC\d{9}", value):
        raise ValueError("KIMDIS official id must look like 26PROC019417347.")
    return value


def require_known_document_identifier(payload: dict[str, Any]) -> str:
    value = str(payload.get("identifier") or payload.get("official_id") or payload.get("eshidis_id") or "").strip()
    if is_kimdis_identifier(value):
        return require_kimdis_id({"official_id": value})
    return require_eshidis_id({"eshidis_id": value})


def require_fetch_identifier(payload: dict[str, Any]) -> str:
    value = str(payload.get("identifier") or payload.get("row_key") or "").strip()
    if authority_row_by_key(value):
        return value
    if value.startswith("AUTHORITY:"):
        return require_authority_row_key({"row_key": value})
    return require_known_document_identifier({"identifier": value})


def require_document_zip_identifier(payload: dict[str, Any]) -> str:
    value = str(payload.get("identifier") or "").strip()
    if value in authority_documents_by_key():
        return value
    if value.startswith("AUTHORITY:") or value.startswith("AUTH-"):
        return value
    return require_known_document_identifier({"identifier": value})


def require_authority_row_key(payload: dict[str, Any]) -> str:
    value = str(payload.get("row_key") or payload.get("identifier") or "").strip()
    if re.fullmatch(r"AUTHORITY:AUTH-[0-9a-f]{16}", value) or re.fullmatch(r"AUTH-[0-9a-f]{16}", value):
        return value if value.startswith("AUTHORITY:") else f"AUTHORITY:{value}"
    raise ValueError("Authority row key must look like AUTHORITY:AUTH-xxxxxxxxxxxxxxxx.")


def require_authority_document_key(payload: dict[str, Any]) -> str:
    value = str(payload.get("row_key") or payload.get("identifier") or "").strip()
    if authority_row_by_key(value) or value in authority_documents_by_key():
        return value
    return require_authority_row_key({"row_key": value})


def require_row_key(payload: dict[str, Any]) -> str:
    value = str(payload.get("row_key") or "").strip()
    if not value or len(value) > 160 or not re.fullmatch(r"[A-Za-z0-9:_\-.]+", value):
        raise ValueError("Invalid row key.")
    return value


def is_kimdis_identifier(value: str) -> bool:
    return re.fullmatch(r"\d{2}PROC\d{9}", str(value or "").strip()) is not None


def status_payload() -> dict[str, Any]:
    document_types_path = REPO_ROOT / "config/document_types.yml"
    document_types_data = load_config(document_types_path) if document_types_path.exists() else {}
    document_types = document_types_data.get("document_types", {}) if isinstance(document_types_data, dict) else {}
    return {
        "repo_root": str(REPO_ROOT),
        "python": sys.executable,
        "reports": {
            "candidates_json": str(REPO_ROOT / "work/reports/eshidis_active_candidates.json"),
            "candidates_markdown": str(REPO_ROOT / "work/reports/eshidis_active_candidates.md"),
        },
        "profiles": [
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in sorted((REPO_ROOT / "config/search_profiles").glob("*.yml"))
        ],
        "evaluation_profiles": [
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in sorted((REPO_ROOT / "config/evaluation_profiles").glob("*.yml"))
        ],
        "document_types": sorted(document_types.keys()) if isinstance(document_types, dict) else [],
    }


def candidates_payload() -> dict[str, Any]:
    path = REPO_ROOT / "work/reports/eshidis_active_candidates.json"
    if not path.exists():
        return {"exists": False, "path": str(path), "candidates": [], "coverage": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "path": str(path),
        "markdown_path": str(REPO_ROOT / "work/reports/eshidis_active_candidates.md"),
        "candidate_status": payload.get("candidate_status"),
        "coverage": payload.get("coverage") or {},
        "candidates": payload.get("candidates") or [],
        "navigation_error": payload.get("navigation_error"),
    }


def dashboard_payload(
    scope: str = "focus",
    sort: str = "deadline_asc",
    as_of: date | None = None,
    *,
    apply_triage: bool = True,
) -> dict[str, Any]:
    all_greece = scope == "all"
    profile = location_focus_profile()
    ignored = ignored_tender_keys()
    triage = ai_triage_by_row_key() if apply_triage else {}
    rows = merged_tender_rows()
    rows = [row for row in rows if str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "") not in ignored]
    rows = [attach_ai_triage(row, triage) for row in rows]
    canonical_rows, duplicate_hidden_rows = suppress_linked_eshidis_duplicates(rows)
    active_rows = [row for row in canonical_rows if dashboard_row_is_active(row, as_of=as_of)]
    triage_hidden = [row for row in active_rows if row.get("ai_triage_hidden")]
    triage_visible_rows = [row for row in active_rows if not row.get("ai_triage_hidden")]
    visible_rows = triage_visible_rows if all_greece else [row for row in triage_visible_rows if row["interest_match"]]
    visible_rows = sort_dashboard_rows(visible_rows, sort=sort)
    return {
        "scope": "all" if all_greece else "focus",
        "sort": sort if sort in {"deadline_asc", "budget_desc"} else "deadline_asc",
        "profile": profile,
        "summary": {
            "total_known": len(rows),
            "visible": len(visible_rows),
            "focus_matches": sum(1 for row in active_rows if row["interest_match"]),
            "verified_active": sum(1 for row in rows if row.get("verified_active")),
            "expired_hidden": len(canonical_rows) - len(active_rows),
            "duplicate_hidden": len(duplicate_hidden_rows),
            "triage_hidden": len(triage_hidden),
            "triage_kept": len(triage_visible_rows),
            "ignored": len(ignored),
        },
        "tenders": visible_rows,
        "discovery_run": latest_discovery_run_payload(),
        "note": (
            "Focus filtering uses configured municipalities, regional units and NUTS hints. "
            "Discovery rows remain candidates until official detail/status verification."
        ),
    }


def suppress_linked_eshidis_duplicates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    canonical_eshidis_ids = {
        str(row.get("eshidis_id") or row.get("display_id") or "")
        for row in rows
        if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ"
        and (str(row.get("source") or "") != "sqlite" or bool(row.get("current_deadline_at")))
        and str(row.get("eshidis_id") or row.get("display_id") or "").isdigit()
    }
    if not canonical_eshidis_ids:
        return rows, []
    kept: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    for row in rows:
        source_label = str(row.get("source_label") or "")
        if source_label == "ΕΣΗΔΗΣ":
            kept.append(row)
            continue
        linked_ids = linked_eshidis_ids_for_row(row)
        duplicate_ids = sorted(canonical_eshidis_ids & set(linked_ids))
        if duplicate_ids:
            hidden.append(
                {
                    **row,
                    "duplicate_hidden": True,
                    "duplicate_reason": f"Duplicate of ESHIDIS {', '.join(duplicate_ids)}",
                }
            )
            continue
        kept.append(row)
    return kept, hidden


def linked_eshidis_ids_for_row(row: dict[str, Any]) -> list[str]:
    values = [str(value) for value in row.get("linked_eshidis_ids") or [] if str(value).strip()]
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    values.extend(str(value) for value in ai.get("eshidis_id_candidates") or [] if str(value).strip())
    return sorted({value for value in values if value.isdigit()})


def ai_triage_report_path() -> Path:
    return REPO_ROOT / "work/reports/ai_triage_report.json"


def ai_triage_by_row_key() -> dict[str, dict[str, Any]]:
    path = ai_triage_report_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    triage: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("row_key") or "")
        ai = row.get("ai")
        if row_key and isinstance(ai, dict):
            triage[row_key] = ai
    return triage


def attach_ai_triage(row: dict[str, Any], triage: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "")
    ai = triage.get(row_key)
    if not ai:
        return {**row, "ai_triage": None, "ai_triage_hidden": False}
    keep = bool(ai.get("keep_for_daily_review"))
    return {
        **row,
        "ai_triage": {
            "decision": ai.get("decision"),
            "confidence": ai.get("confidence"),
            "reason": ai.get("reason"),
            "eshidis_id_candidates": ai.get("eshidis_id_candidates") or [],
        },
        "ai_triage_hidden": not keep,
    }


def ignored_tenders_path() -> Path:
    return REPO_ROOT / "work/derived/ignored_tenders.json"


def ignored_tender_keys() -> set[str]:
    path = ignored_tenders_path()
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(item.get("row_key") or "") for item in payload.get("ignored") or [] if isinstance(item, dict)}


def dismiss_tender(row_key: str) -> dict[str, Any]:
    path = ignored_tenders_path()
    existing = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        existing = [item for item in payload.get("ignored") or [] if isinstance(item, dict)]
    if not any(item.get("row_key") == row_key for item in existing):
        existing.append({"row_key": row_key, "ignored_at": utc_now_iso()})
    payload = {"updated_at": utc_now_iso(), "ignored": existing}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "row_key": row_key, "ignored": len(existing), "dashboard": dashboard_payload(scope="focus")}


def discovery_history_path() -> Path:
    return REPO_ROOT / "work/derived/discovery_runs.json"


def latest_discovery_run_payload() -> dict[str, Any] | None:
    return latest_discovery_run(discovery_history_path())


def location_focus_profile() -> dict[str, Any]:
    path = REPO_ROOT / "config" / "locations.yml"
    data = load_config(path) if path.exists() else {}
    municipalities = data.get("municipalities", []) if isinstance(data, dict) else []
    regions = data.get("regions", []) if isinstance(data, dict) else []
    return {
        "label": "Περιοχή ενδιαφέροντος",
        "municipalities": [item.get("name") for item in municipalities if isinstance(item, dict)],
        "regions": [
            {
                "name": item.get("name"),
                "regional_units": item.get("included_regional_units") or [],
            }
            for item in regions
            if isinstance(item, dict)
        ],
    }


def merged_tender_rows() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in authority_candidate_rows():
        row_key = str(candidate.get("row_key") or "")
        if row_key:
            merged[row_key] = candidate
    for candidate in kimdis_open_proc_rows():
        official_id = str(candidate.get("official_id") or "")
        if official_id:
            existing = merged.get(f"KIMDIS:{official_id}", {})
            merged[f"KIMDIS:{official_id}"] = {**existing, **candidate}
    for candidate in discovery_candidate_rows():
        eshidis_id = str(candidate.get("eshidis_id") or "")
        if eshidis_id:
            merged[eshidis_id] = candidate
    for tender in sqlite_tender_rows():
        eshidis_id = str(tender.get("eshidis_id") or "")
        if eshidis_id:
            existing = merged.get(eshidis_id, {})
            merged[eshidis_id] = {**existing, **{key: value for key, value in tender.items() if value not in (None, "")}}
    rows = [decorate_tender_row(row) for row in merged.values()]
    return sorted(rows, key=lambda row: (row.get("deadline_sort") or "9999", row.get("display_id") or ""))


def expanded_report_payload() -> dict[str, Any]:
    path = REPO_ROOT / "work/reports/expanded_discovery_report.json"
    if not path.exists():
        return {"exists": False, "path": str(path), "focus_open_proc_candidates": [], "focus_authority_candidates": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "path": str(path),
        "markdown_path": str(REPO_ROOT / "work/reports/expanded_discovery_report.md"),
        "summary": payload.get("summary") or {},
        "focus_open_proc_candidates": payload.get("focus_open_proc_candidates") or [],
        "focus_authority_candidates": payload.get("focus_authority_candidates") or [],
    }


def authority_candidate_rows() -> list[dict[str, Any]]:
    payload = expanded_report_payload()
    rows = []
    for candidate in payload.get("focus_authority_candidates", []):
        if not isinstance(candidate, dict):
            continue
        official_id = str(candidate.get("official_id") or "").strip()
        record_type = str(candidate.get("record_type") or "")
        if not official_id:
            continue
        is_kimdis = is_kimdis_identifier(official_id)
        is_eshidis = official_id.isdigit() and 5 <= len(official_id) <= 7
        row_key = f"KIMDIS:{official_id}" if is_kimdis else official_id if is_eshidis else f"AUTHORITY:{official_id}"
        authority_docs = authority_documents_by_key().get(row_key, [])
        attachment_urls = [str(url) for url in candidate.get("attachment_urls") or [] if str(url).strip()]
        if not attachment_urls and candidate.get("attachment_url"):
            attachment_urls = [str(candidate.get("attachment_url"))]
        rows.append(
            {
                "source": "authority",
                "source_label": "Φορέας",
                "row_key": row_key,
                "official_id": official_id,
                "eshidis_id": official_id if is_eshidis else None,
                "display_id": official_id,
                "title": candidate.get("title"),
                "authority_name": candidate.get("authority"),
                "region": ", ".join(candidate.get("matched_scopes") or []),
                "budget_with_vat": candidate.get("budget"),
                "current_deadline_at": candidate.get("submission_deadline"),
                "published_at": candidate.get("published_at"),
                "status": candidate.get("status"),
                "status_confidence": 0.0,
                "row_text": " ".join(
                    str(candidate.get(key) or "")
                    for key in ("title", "authority", "published_at", "source_url", "attachment_url", "matched_scopes", "match_notes")
                ),
                "official_url": candidate.get("source_url"),
                "attachment_url": candidate.get("attachment_url"),
                "attachment_urls": attachment_urls,
                "download_url": f"/api/authority-document-file?row_key={row_key}&index=0" if authority_docs else candidate.get("attachment_url"),
                "preview_url": f"/api/authority-document-preview?row_key={row_key}" if authority_docs else None,
                "has_local_documents": bool(authority_docs),
                "local_document_count": len(authority_docs),
                "supports_eshidis_actions": is_eshidis,
                "supports_kimdis_actions": is_kimdis,
                "supports_authority_actions": bool(attachment_urls),
                "interest_match": bool(candidate.get("matched_scopes")),
                "interest_reason": ", ".join([*(candidate.get("matched_scopes") or []), *(candidate.get("match_notes") or [])]),
                "authority_record_type": record_type,
            }
        )
    return rows


def authority_row_by_key(row_key: str) -> dict[str, Any] | None:
    for row in authority_candidate_rows():
        if row.get("row_key") == row_key:
            return row
    return None


def authority_document_index_path() -> Path:
    return REPO_ROOT / "work/derived/authority_documents.json"


def authority_document_index_payload() -> dict[str, Any]:
    path = authority_document_index_path()
    if not path.exists():
        return {"exists": False, "path": str(path), "documents": []}
    return json.loads(path.read_text(encoding="utf-8"))


def authority_documents_by_key() -> dict[str, list[dict[str, Any]]]:
    payload = authority_document_index_payload()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for document in payload.get("documents") or []:
        if not isinstance(document, dict):
            continue
        row_key = str(document.get("row_key") or "")
        if row_key:
            grouped.setdefault(row_key, []).append(document)
    return grouped


def write_authority_document_index(row_key: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    path = authority_document_index_path()
    existing = authority_document_index_payload()
    retained = [
        item
        for item in existing.get("documents", [])
        if isinstance(item, dict) and item.get("row_key") != row_key
    ]
    payload = {
        "updated_at": utc_now_iso(),
        "documents": [*retained, *documents],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def authority_download_dir(row_key: str) -> Path:
    return REPO_ROOT / "work/download_audit/authority" / safe_filename(row_key)


def download_authority_document(url: str, target_dir: Path, index: int) -> tuple[Path, int]:
    request = Request(url, headers={"User-Agent": "TenderRadar/0.1 authority-document-fetch"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
    name = safe_filename(unquote(Path(urlparse(url).path).name or f"document_{index + 1}.bin"))
    path = target_dir / unique_archive_name(name, {item.name for item in target_dir.iterdir() if item.is_file()})
    path.write_bytes(body)
    return path, len(body)


def kimdis_open_proc_rows() -> list[dict[str, Any]]:
    payload = expanded_report_payload()
    document_index = kimdis_documents_by_official_id()
    rows = []
    for candidate in payload.get("focus_open_proc_candidates", []):
        if not isinstance(candidate, dict):
            continue
        official_id = str(candidate.get("official_id") or "").strip()
        if not official_id:
            continue
        deadline = str(candidate.get("submission_deadline") or "")
        matched_scopes = [str(scope) for scope in candidate.get("matched_scopes") or [] if str(scope).strip()]
        match_notes = [str(note) for note in candidate.get("match_notes") or [] if str(note).strip()]
        document = document_index.get(official_id, {})
        linked_eshidis_ids = [str(value) for value in document.get("linked_eshidis_ids") or [] if str(value).strip()]
        local_path = normalize_local_path(_none_or_str(document.get("local_path")))
        has_local_document = local_path is not None
        text_sample = None
        analysis = document.get("document_analysis") if isinstance(document.get("document_analysis"), dict) else {}
        if isinstance(analysis, dict):
            text_sample = analysis.get("text_sample")
        rows.append(
            {
                "source": "kimdis",
                "source_label": "ΚΗΜΔΗΣ",
                "row_key": f"KIMDIS:{official_id}",
                "official_id": official_id,
                "display_id": official_id,
                "title": candidate.get("title"),
                "authority_name": candidate.get("authority"),
                "region": ", ".join(matched_scopes),
                "budget_with_vat": candidate.get("budget"),
                "current_deadline_at": deadline,
                "status": candidate.get("status"),
                "status_confidence": 0.65,
                "row_text": " ".join(
                    str(candidate.get(key) or "")
                    for key in ("title", "authority", "budget", "submission_deadline", "matched_scopes", "match_notes", "status")
                ),
                "official_url": candidate.get("source_url"),
                "attachment_url": candidate.get("attachment_url"),
                "download_url": f"/api/kimdis-document-file?official_id={official_id}" if has_local_document else candidate.get("attachment_url"),
                "preview_url": f"/api/kimdis-document-preview?official_id={official_id}" if has_local_document else None,
                "has_local_documents": has_local_document,
                "local_path": str(local_path) if local_path else None,
                "sha256": document.get("sha256"),
                "size_bytes": document.get("size_bytes"),
                "text_sample": short_text_sample(_none_or_str(text_sample)),
                "linked_eshidis_ids": linked_eshidis_ids,
                "supports_eshidis_actions": False,
                "supports_kimdis_actions": True,
                "interest_match": bool(matched_scopes),
                "interest_reason": ", ".join([*matched_scopes, *match_notes]),
            }
        )
    return rows


def kimdis_document_index_payload() -> dict[str, Any]:
    path = REPO_ROOT / "work/derived/kimdis_open_proc_documents.json"
    if not path.exists():
        return {"exists": False, "path": str(path), "documents": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "path": str(path),
        "documents": payload.get("documents") or [],
        "summary": payload.get("fetch_report_summary") or {},
        "status_note": payload.get("status_note"),
    }


def kimdis_documents_by_official_id() -> dict[str, dict[str, Any]]:
    payload = kimdis_document_index_payload()
    documents = {}
    for document in payload.get("documents", []):
        if not isinstance(document, dict):
            continue
        official_id = str(document.get("official_id") or "")
        if official_id:
            documents[official_id] = document
    return documents


def discovery_candidate_rows() -> list[dict[str, Any]]:
    payload = candidates_payload()
    rows = []
    for candidate in payload.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        row_text = str(candidate.get("row_text") or "")
        rows.append(
            {
                "source": "discovery",
                "eshidis_id": candidate.get("eshidis_id"),
                "title": candidate.get("title"),
                "authority_name": candidate.get("authority_name"),
                "region": extract_region(row_text),
                "budget_with_vat": parse_budget_from_row_text(row_text),
                "current_deadline_at": candidate.get("submission_deadline"),
                "status": candidate.get("status"),
                "status_confidence": candidate.get("status_confidence"),
                "row_text": row_text,
            }
        )
    return rows


def sqlite_tender_rows() -> list[dict[str, Any]]:
    db_path = REPO_ROOT / "data" / "tender_radar.sqlite"
    if not db_path.exists():
        return []
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT eshidis_id, title, authority_name, region, budget_with_vat,
                   current_deadline_at, status, status_confidence
            FROM tenders
            WHERE eshidis_id IS NOT NULL
            ORDER BY eshidis_id
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "source": "sqlite",
            "eshidis_id": row["eshidis_id"],
            "title": row["title"],
            "authority_name": row["authority_name"],
            "region": row["region"],
            "budget_with_vat": row["budget_with_vat"],
            "current_deadline_at": row["current_deadline_at"],
            "status": row["status"],
            "status_confidence": row["status_confidence"],
            "row_text": " ".join(str(row[key] or "") for key in row.keys()),
        }
        for row in rows
    ]


def decorate_tender_row(row: dict[str, Any]) -> dict[str, Any]:
    eshidis_id = str(row.get("eshidis_id") or "")
    row_key = str(row.get("row_key") or eshidis_id or row.get("display_id") or "")
    text = " ".join(
        str(row.get(key) or "")
        for key in ("title", "authority_name", "region", "row_text")
    )
    return {
        **row,
        "row_key": row_key,
        "display_id": row.get("display_id") or eshidis_id,
        "source_label": row.get("source_label") or ("ΕΣΗΔΗΣ" if eshidis_id else row.get("source") or ""),
        "interest_match": bool(row.get("interest_match")) or is_interest_match(text),
        "interest_reason": row.get("interest_reason") or interest_reason(text),
        "budget_display": format_budget(row.get("budget_with_vat")),
        "budget_sort": budget_sort_value(row.get("budget_with_vat")),
        "deadline_display": deadline_display(str(row.get("current_deadline_at") or row.get("submission_deadline") or "")),
        "deadline_sort": deadline_sort_key(str(row.get("current_deadline_at") or "")),
        "official_url": row.get("official_url") or (official_resource_url(eshidis_id) if eshidis_id else None),
        "supports_eshidis_actions": bool(row.get("supports_eshidis_actions", True) and eshidis_id),
        "verified_active": False,
    }


def document_preview_payload(eshidis_id: str) -> dict[str, Any]:
    db_path = REPO_ROOT / "data" / "tender_radar.sqlite"
    if not db_path.exists():
        return {"eshidis_id": eshidis_id, "documents": []}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT attachments.id AS attachment_id, attachments.original_name,
                   attachments.local_path, attachments.size_bytes, attachments.sha256,
                   documents.document_type, documents.text_sample
            FROM attachments
            JOIN tenders ON tenders.id = attachments.tender_id
            LEFT JOIN documents ON documents.attachment_id = attachments.id
            WHERE tenders.eshidis_id = ?
              AND attachments.is_latest = 1
            ORDER BY attachments.id
            """,
            (eshidis_id,),
        ).fetchall()
    finally:
        connection.close()
    docs = [preview_document_from_row(row) for row in rows]
    priority = {"declaration": 0, "technical_description": 1, "budget": 2, "price_list": 3}
    docs.sort(key=lambda item: (priority.get(str(item["kind"]), 9), item["name"]))
    return {
        "eshidis_id": eshidis_id,
        "official_url": official_resource_url(eshidis_id),
        "documents": docs,
        "featured": [doc for doc in docs if doc["kind"] in {"declaration", "technical_description", "budget"}],
    }


def kimdis_document_preview_payload(official_id: str) -> dict[str, Any]:
    document = kimdis_documents_by_official_id().get(official_id)
    if not document:
        return {"official_id": official_id, "documents": [], "featured": []}
    local_path = normalize_local_path(_none_or_str(document.get("local_path")))
    analysis = document.get("document_analysis") if isinstance(document.get("document_analysis"), dict) else {}
    evidence = document.get("document_evidence") if isinstance(document.get("document_evidence"), dict) else {}
    kind = preview_kind(str(analysis.get("document_type") or ""), str(document.get("original_filename") or ""))
    doc = {
        "official_id": official_id,
        "name": document.get("original_filename") or f"{official_id}.pdf",
        "kind": kind,
        "label": preview_label(kind),
        "document_type": analysis.get("document_type"),
        "available": local_path is not None,
        "size_bytes": document.get("size_bytes"),
        "sha256": document.get("sha256"),
        "text_sample": short_text_sample(_none_or_str(analysis.get("text_sample"))),
        "evidence_status": evidence.get("evidence_status"),
        "authority_match": evidence.get("authority_match"),
        "scope_alias_matches": evidence.get("scope_alias_matches") or [],
        "view_url": f"/api/kimdis-document-file?official_id={official_id}" if local_path else None,
    }
    linked_eshidis_ids = [str(value) for value in document.get("linked_eshidis_ids") or [] if str(value).strip()]
    linked_eshidis_file_count = sum(len(eshidis_document_paths(eshidis_id)) for eshidis_id in linked_eshidis_ids)
    return {
        "official_id": official_id,
        "source_label": "ΚΗΜΔΗΣ",
        "official_url": document.get("attachment_url") or document.get("source_url"),
        "candidate_status": document.get("candidate_status"),
        "verification_status": document.get("verification_status"),
        "linked_eshidis_ids": linked_eshidis_ids,
        "linked_eshidis_file_count": linked_eshidis_file_count,
        "documents": [doc],
        "featured": [doc],
    }


def authority_document_preview_payload(row_key: str) -> dict[str, Any]:
    row = authority_row_by_key(row_key) or {}
    documents = authority_documents_by_key().get(row_key, [])
    docs = []
    for index, document in enumerate(documents):
        local_path = normalize_local_path(_none_or_str(document.get("local_path")))
        kind = preview_kind("", str(document.get("original_filename") or ""))
        docs.append(
            {
                "index": index,
                "name": document.get("original_filename"),
                "kind": kind,
                "label": preview_label(kind),
                "available": local_path is not None,
                "size_bytes": document.get("size_bytes"),
                "source_url": document.get("attachment_url"),
                "view_url": f"/api/authority-document-file?row_key={row_key}&index={index}" if local_path else document.get("attachment_url"),
            }
        )
    return {
        "row_key": row_key,
        "source_label": "Φορέας",
        "official_url": row.get("official_url") or row.get("attachment_url"),
        "candidate_status": row.get("status"),
        "documents": docs,
        "featured": [doc for doc in docs if doc["kind"] in {"declaration", "technical_description", "budget", "price_list"}],
    }


def preview_document_from_row(row: sqlite3.Row) -> dict[str, Any]:
    attachment_id = int(row["attachment_id"])
    local_path = normalize_local_path(row["local_path"])
    available = local_path is not None and local_path.exists()
    kind = preview_kind(str(row["document_type"] or ""), str(row["original_name"] or ""))
    return {
        "attachment_id": attachment_id,
        "name": row["original_name"],
        "kind": kind,
        "label": preview_label(kind),
        "document_type": row["document_type"],
        "available": available,
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "text_sample": short_text_sample(row["text_sample"]),
        "view_url": f"/api/document-file?attachment_id={attachment_id}" if available else None,
    }


def local_attachment_path(attachment_id: int) -> Path | None:
    db_path = REPO_ROOT / "data" / "tender_radar.sqlite"
    if attachment_id <= 0 or not db_path.exists():
        return None
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT local_path FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    finally:
        connection.close()
    if not row:
        return None
    return normalize_local_path(row[0])


def kimdis_document_file_path(official_id: str) -> Path | None:
    document = kimdis_documents_by_official_id().get(official_id)
    if not document:
        return None
    return normalize_local_path(_none_or_str(document.get("local_path")))


def authority_document_file_path(row_key: str, index: int) -> Path | None:
    documents = authority_documents_by_key().get(row_key, [])
    if index < 0 or index >= len(documents):
        return None
    return normalize_local_path(_none_or_str(documents[index].get("local_path")))


def kimdis_linked_eshidis_ids(official_id: str) -> list[str]:
    document = kimdis_documents_by_official_id().get(official_id)
    if not document:
        return []
    linked: list[str] = []
    for value in document.get("linked_eshidis_ids") or []:
        text = str(value or "").strip()
        if text.isdigit() and 5 <= len(text) <= 7 and text not in linked:
            linked.append(text)
    return linked


def document_zip_bytes(identifier: str) -> tuple[str, bytes | None]:
    if identifier in authority_documents_by_key():
        entries = authority_document_paths(identifier)
    elif identifier.startswith("AUTHORITY:") or identifier.startswith("AUTH-"):
        authority_key = require_authority_row_key({"row_key": identifier})
        entries = authority_document_paths(authority_key)
    elif is_kimdis_identifier(identifier):
        entries = kimdis_document_paths(identifier)
    else:
        entries = eshidis_document_paths(require_eshidis_id({"eshidis_id": identifier}))
    if not entries:
        return f"tender_{safe_filename(identifier)}_documents.zip", None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used_names: set[str] = set()
        for preferred_name, path in entries:
            arcname = unique_archive_name(safe_filename(preferred_name or path.name), used_names)
            archive.write(path, arcname=arcname)
    return f"tender_{safe_filename(identifier)}_documents.zip", buffer.getvalue()


def eshidis_document_paths(eshidis_id: str) -> list[tuple[str, Path]]:
    db_path = REPO_ROOT / "data" / "tender_radar.sqlite"
    if not db_path.exists():
        return []
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT original_name, local_path
            FROM attachments
            JOIN tenders ON tenders.id = attachments.tender_id
            WHERE tenders.eshidis_id = ?
              AND attachments.is_latest = 1
              AND attachments.local_path IS NOT NULL
            ORDER BY attachments.id
            """,
            (eshidis_id,),
        ).fetchall()
    finally:
        connection.close()
    entries: list[tuple[str, Path]] = []
    for row in rows:
        path = normalize_local_path(row["local_path"])
        if path:
            entries.append((str(row["original_name"] or path.name), path))
    return entries


def kimdis_document_paths(official_id: str) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    document_path = kimdis_document_file_path(official_id)
    if document_path:
        entries.append((document_path.name, document_path))
    target_dir = (REPO_ROOT / "work/download_audit/kimdis" / safe_filename(official_id)).resolve()
    work_dir = (REPO_ROOT / "work").resolve()
    if work_dir in target_dir.parents and target_dir.exists():
        for path in sorted(target_dir.iterdir()):
            if path.is_file() and path.resolve() != document_path:
                entries.append((path.name, path.resolve()))
    for eshidis_id in kimdis_linked_eshidis_ids(official_id):
        for preferred_name, path in eshidis_document_paths(eshidis_id):
            entries.append((f"ESHIDIS_{eshidis_id}_{preferred_name}", path))
    return entries


def authority_document_paths(row_key: str) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for document in authority_documents_by_key().get(row_key, []):
        path = normalize_local_path(_none_or_str(document.get("local_path")))
        if path:
            entries.append((str(document.get("original_filename") or path.name), path))
    return entries


def safe_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip())
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    return sanitized or "document"


def unique_archive_name(name: str, used_names: set[str]) -> str:
    candidate = name
    stem = Path(name).stem or "document"
    suffix = Path(name).suffix
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


def normalize_local_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value).replace("\\", "/"))
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    work_dir = (REPO_ROOT / "work").resolve()
    if work_dir not in path.parents or not path.exists():
        return None
    return path


def _none_or_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def is_interest_match(text: str) -> bool:
    return interest_reason(text) is not None


def interest_reason(text: str) -> str | None:
    normalized = normalize_greek(text)
    data = load_config(REPO_ROOT / "config" / "locations.yml")
    for municipality in data.get("municipalities", []):
        if not isinstance(municipality, dict):
            continue
        terms = [municipality.get("name"), *(municipality.get("aliases") or [])]
        if any(term and focus_term_matches(normalized, str(term)) for term in terms):
            return str(municipality.get("name") or "Δήμος ενδιαφέροντος")
        ambiguous_reason = ambiguous_location_reason(normalized, municipality)
        if ambiguous_reason:
            return ambiguous_reason
    for region in data.get("regions", []):
        if not isinstance(region, dict):
            continue
        included_units = [str(unit) for unit in region.get("included_regional_units") or [] if str(unit).strip()]
        terms = included_units or [region.get("name"), *(region.get("nuts_prefixes") or [])]
        if any(term and focus_term_matches(normalized, str(term), prefix_ok=not included_units) for term in terms):
            units = ", ".join(region.get("included_regional_units") or [])
            return f"{region.get('name')} - {units}" if units else str(region.get("name"))
    return None


def ambiguous_location_reason(normalized_text: str, scope: dict[str, Any]) -> str | None:
    for rule in scope.get("ambiguous_aliases") or []:
        if not isinstance(rule, dict) or not rule.get("alias"):
            continue
        if not focus_term_matches(normalized_text, str(rule.get("alias"))):
            continue
        negative_context = [str(value) for value in rule.get("negative_context") or [] if str(value).strip()]
        if any(focus_term_matches(normalized_text, value) for value in negative_context):
            continue
        positive_context = [str(value) for value in rule.get("positive_context") or [] if str(value).strip()]
        name = str(scope.get("name") or "Περιοχή ενδιαφέροντος")
        if any(focus_term_matches(normalized_text, value) for value in positive_context):
            return name
        return f"{name} (ασαφές τοπωνύμιο: {rule.get('alias')})"
    return None


def focus_term_matches(normalized_text: str, term: str, *, prefix_ok: bool = False) -> bool:
    normalized_term = normalize_greek(term)
    if not normalized_term:
        return False
    if normalized_term.startswith("el"):
        return normalized_text.find(normalized_term) >= 0 if prefix_ok else normalized_term in normalized_text
    if len(normalized_term) <= 3:
        pattern = rf"(?<![0-9a-zα-ω]){re.escape(normalized_term)}(?![0-9a-zα-ω])"
        return re.search(pattern, normalized_text) is not None
    if " " in normalized_term:
        pattern = rf"(?<![0-9a-zα-ω]){re.escape(normalized_term)}(?![0-9a-zα-ω])"
        return re.search(pattern, normalized_text) is not None
    return normalized_term in normalized_text


def normalize_greek(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    normalized = unicodedata.normalize("NFC", without_accents)
    return re.sub(r"\s+", " ", normalized).strip()


def parse_budget_from_row_text(row_text: str) -> float | None:
    before_first_date = re.split(r"\d{2}-\d{2}-\d{4}", row_text, maxsplit=1)[0]
    matches = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", before_first_date)
    if not matches:
        return None
    return greek_number_to_float(matches[-1])


def greek_number_to_float(value: str) -> float | None:
    try:
        return float(value.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def format_budget(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    integer, decimals = f"{number:,.2f}".split(".")
    return integer.replace(",", ".") + "," + decimals + " EUR"


def budget_sort_value(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return float(value)
    return greek_number_to_float(str(value)) if "," in str(value) else _float_or_none(value)


def extract_region(row_text: str) -> str | None:
    match = re.search(r"(EL\d{3}\s+-\s+[^Υ]+?)(?:\s+ΥΠΟΒΟΛΗ|\s+ΣΕ\s+|\s+ΕΛΕΓΧΟΣ|$)", row_text)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


def sort_dashboard_rows(rows: list[dict[str, Any]], *, sort: str) -> list[dict[str, Any]]:
    if sort == "budget_desc":
        return sorted(
            rows,
            key=lambda row: (
                row.get("budget_sort") is None,
                -(float(row.get("budget_sort") or 0)),
                row.get("deadline_sort") or "9999",
                row.get("display_id") or "",
            ),
        )
    return sorted(rows, key=lambda row: (row.get("deadline_sort") or "9999", row.get("display_id") or ""))


def dashboard_row_is_active(row: dict[str, Any], *, as_of: date | None = None) -> bool:
    deadline = deadline_date(str(row.get("current_deadline_at") or row.get("submission_deadline") or ""))
    if deadline is None:
        return True
    return deadline >= (as_of or date.today())


def deadline_date(value: str) -> date | None:
    sort_key = deadline_sort_key(value)
    if sort_key == "9999":
        return None
    try:
        return date.fromisoformat(sort_key[:10])
    except ValueError:
        return None


def deadline_sort_key(value: str) -> str:
    match = re.match(r"(\d{2})-(\d{2})-(\d{4})(.*)", value or "")
    if match:
        day, month, year, rest = match.groups()
        return f"{year}-{month}-{day}{rest}"
    iso_match = re.match(r"(\d{4})-(\d{2})-(\d{2})T?(.*)", value or "")
    if iso_match:
        year, month, day, rest = iso_match.groups()
        return f"{year}-{month}-{day} {rest}".strip()
    return "9999"


def deadline_display(value: str) -> str:
    iso_match = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?", value or "")
    if iso_match:
        year, month, day, time = iso_match.groups()
        return f"{day}-{month}-{year} {time}"
    return value


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def official_resource_url(eshidis_id: str) -> str:
    return f"https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{eshidis_id}"


def preview_kind(document_type: str, name: str) -> str:
    normalized = normalize_greek(f"{document_type} {name}")
    if document_type == "tender_declaration" or "διακηρυ" in normalized:
        return "declaration"
    if document_type == "technical_description" or "τεχνικη περιγραφ" in normalized:
        return "technical_description"
    if document_type == "budget" or "προυπολογισ" in normalized or "προϋπολογισ" in normalized:
        return "budget"
    if document_type == "price_list" or "τιμολογιο" in normalized:
        return "price_list"
    return "other"


def preview_label(kind: str) -> str:
    return {
        "declaration": "Διακήρυξη",
        "technical_description": "Τεχνική περιγραφή",
        "budget": "Προϋπολογισμός",
        "price_list": "Τιμολόγιο",
    }.get(kind, "Λοιπό αρχείο")


def short_text_sample(value: str | None, limit: int = 420) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def report_path(value: str) -> Path | None:
    if value not in {"candidates.md", "candidates.json"}:
        return None
    name = "eshidis_active_candidates.md" if value == "candidates.md" else "eshidis_active_candidates.json"
    path = (REPO_ROOT / "work/reports" / name).resolve()
    reports_dir = (REPO_ROOT / "work/reports").resolve()
    if reports_dir not in path.parents or not path.exists():
        return None
    return path


def content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json; charset=utf-8"
    if suffix in {".md", ".markdown"}:
        return "text/markdown; charset=utf-8"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in {"application/javascript", "application/xml"}:
        return f"{content_type}; charset=utf-8"
    return content_type


def safe_evaluation_profile_path(value: str) -> Path:
    relative = value or "config/evaluation_profiles/public_works_dynamic.yml"
    if "\\" in relative:
        relative = relative.replace("\\", "/")
    path = (REPO_ROOT / relative).resolve()
    profiles_dir = (REPO_ROOT / "config/evaluation_profiles").resolve()
    if profiles_dir not in path.parents or path.suffix.lower() not in {".yml", ".yaml"}:
        raise ValueError("Unknown evaluation profile path.")
    if not path.exists():
        raise ValueError("Evaluation profile does not exist.")
    return path


def evaluation_profile_payload(path: Path) -> dict[str, Any]:
    data = load_config(path)
    if not isinstance(data, dict):
        raise ValueError("Evaluation profile must be a YAML mapping.")
    normalized = normalize_evaluation_config(data, fallback_id=path.stem)
    return {
        "ok": True,
        "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "data": normalized,
    }


INDEX_HTML = """<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tender Radar</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <aside class="sidebar">
    <div class="brand">
      <span class="mark">TR</span>
      <div>
        <h1>Tender Radar</h1>
        <p>Δημόσια έργα</p>
      </div>
    </div>
    <nav>
      <button class="nav active" data-view="overview">Αναζήτηση</button>
      <button class="nav" data-view="rules">Κανόνες</button>
      <button class="nav" data-view="reports">Αρχεία</button>
    </nav>
  </aside>
  <main>
    <header class="topbar">
      <div>
        <p class="eyebrow">Public Works Tender Radar</p>
        <h2>Διαγωνισμοί που αξίζει να κοιτάξεις πρώτα</h2>
        <p id="statusText">Έτοιμο</p>
      </div>
      <button id="refreshBtn" class="secondary">Ανανέωση</button>
    </header>

    <section id="overview" class="view active">
      <div class="searchBand">
        <div>
          <p class="eyebrow">Περιοχή αναζήτησης</p>
          <h3>Ναυπακτία, Δωρίδα, Θέρμο, Μεσολόγγι, Πάτρα και σχετικές Π.Ε.</h3>
          <p id="scopeText" class="mutedLine">Προεπιλογή: τοπική περιοχή ενδιαφέροντος από το config.</p>
          <p class="mutedLine">Η γρήγορη αναζήτηση είναι bounded: έως 100 ενεργές γραμμές ΕΣΗΔΗΣ και 20 σελίδες ΚΗΜΔΗΣ ανά οικογένεια εγγράφων.</p>
          <p id="discoverySafetyText" class="mutedLine">Δεν υπάρχει ακόμα καταγεγραμμένο discovery watermark σε αυτό το runtime.</p>
        </div>
        <label class="switchLine">
          <input id="allGreeceToggle" type="checkbox">
          <span>Λήψη έργων από όλη την Ελλάδα</span>
        </label>
        <div class="toolbar inlineToolbar">
          <label>Βάθος ΕΣΗΔΗΣ <input id="limitInput" type="number" min="1" max="500" value="100"></label>
          <label>Ταξινόμηση
            <select id="sortSelect">
              <option value="deadline_asc">Λήγει πιο άμεσα</option>
              <option value="budget_desc">Μεγαλύτερος προϋπολογισμός</option>
            </select>
          </label>
          <label class="switchLine inlineSwitch">
            <input id="backfillToggle" type="checkbox">
            <span>Backfill safety</span>
          </label>
          <button id="discoverBtn">Νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ</button>
        </div>
      </div>

      <div class="metrics">
        <div><span id="visibleTenderCount">0</span><small>έργα στη λίστα</small></div>
        <div><span id="focusTenderCount">0</span><small>ταιριάζουν στην περιοχή</small></div>
      </div>

      <div class="workspace">
        <div class="tableWrap">
          <table class="tenderTable">
            <thead>
              <tr>
                <th>Α/Α</th>
                <th>Πηγή</th>
                <th>Έργο</th>
                <th>Φορέας</th>
                <th>Προϋπολογισμός</th>
                <th>Λήξη</th>
                <th>Ενέργειες</th>
              </tr>
            </thead>
            <tbody id="tenderRows"></tbody>
          </table>
        </div>
        <aside class="previewPane">
          <div class="previewHeader">
            <div>
              <p class="eyebrow">Preview</p>
              <h3 id="previewTitle">Διάλεξε έργο</h3>
            </div>
            <a id="officialLink" class="iconLink" target="_blank" rel="noreferrer">ΕΣΗΔΗΣ</a>
          </div>
          <div id="previewBody" class="previewBody">
            <p class="mutedLine">Εδώ θα εμφανιστούν η διακήρυξη, η τεχνική περιγραφή και ο προϋπολογισμός όταν υπάρχουν κατεβασμένα ή γνωστά συνημμένα.</p>
          </div>
        </aside>
      </div>
      <details class="commandLog">
        <summary>Τεχνικό αποτέλεσμα τελευταίας ενέργειας</summary>
        <pre id="commandOutput"></pre>
      </details>
    </section>

    <section id="workflow" class="view">
      <div class="toolbar">
        <label>A/A ΕΣΗΔΗΣ <input id="eshidisInput" type="text" inputmode="numeric" placeholder="π.χ. 221744"></label>
        <button id="fetchBtn">Fetch official detail</button>
        <button id="downloadBtn" class="secondary">Download files</button>
        <button id="analyzeBtn" class="secondary">Analyze docs</button>
      </div>
      <div class="toolbar compact">
        <label>ΑΔΑΜ ΚΗΜΔΗΣ <input id="kimdisInput" type="text" inputmode="text" placeholder="π.χ. 26PROC019417347"></label>
        <button id="kimdisPreviewBtn" class="secondary">Preview KIMDIS</button>
        <button id="kimdisFetchBtn">Fetch KIMDIS files</button>
      </div>
      <div class="toolbar compact">
        <label>Search profile <select id="profileSelect"></select></label>
        <button id="searchBtn">Run search</button>
      </div>
      <div class="toolbar compact">
        <label>Evaluation <select id="evaluationProfileSelect"></select></label>
        <button id="evaluateBtn">Evaluate</button>
      </div>
      <pre id="advancedCommandOutput"></pre>
    </section>

    <section id="rules" class="view">
      <div class="toolbar">
        <label>Evaluation profile <select id="ruleProfileSelect"></select></label>
        <button id="loadRulesBtn" class="secondary">Load</button>
        <button id="saveRulesBtn">Save Rules</button>
      </div>
      <div class="rulesGrid">
        <div class="panel">
          <div class="panelHeader">
            <h3>Rules</h3>
            <button id="newRuleBtn" class="secondary">New</button>
          </div>
          <div id="ruleList" class="ruleList"></div>
        </div>
        <div class="panel">
          <div class="panelHeader">
            <h3>Rule editor</h3>
            <button id="deleteRuleBtn" class="secondary">Delete</button>
          </div>
          <div class="editorGrid">
            <label>Rule id <input id="ruleIdInput" type="text" placeholder="foundation_excavation_price_gt_5"></label>
            <label>Label <input id="ruleLabelInput" type="text" placeholder="Εκσκαφές θεμελίων > 5 ευρώ"></label>
            <label>Severity
              <select id="ruleSeverityInput">
                <option value="info">info</option>
                <option value="important">important</option>
                <option value="critical">critical</option>
              </select>
            </label>
            <label>Score <input id="ruleScoreInput" type="number" step="0.5" value="1"></label>
            <label>Document types <input id="ruleDocumentTypesInput" type="text" placeholder="budget, price_list"></label>
            <label>Numeric filter
              <span class="inlineControls">
                <select id="ruleOperatorInput">
                  <option value="">none</option>
                  <option value=">">&gt;</option>
                  <option value=">=">&gt;=</option>
                  <option value="<">&lt;</option>
                  <option value="<=">&lt;=</option>
                  <option value="=">=</option>
                </select>
                <input id="ruleThresholdInput" type="number" step="0.01" placeholder="5.00">
              </span>
            </label>
            <label class="wide">Phrases <textarea id="rulePhrasesInput" rows="6" placeholder="μία φράση ανά γραμμή"></textarea></label>
          </div>
          <div class="toolbar editorActions">
            <button id="applyRuleBtn">Apply Rule</button>
            <span id="rulesStatus" class="noteText">Load a profile to edit rules.</span>
          </div>
        </div>
      </div>
    </section>

    <section id="reports" class="view">
      <div class="toolbar">
        <a class="button" href="/api/report?path=candidates.md" target="_blank">Open Candidates Markdown</a>
        <a class="button secondary" href="/api/report?path=candidates.json" target="_blank">Open Candidates JSON</a>
      </div>
      <p class="note">Οι υποψήφιοι μένουν candidate-only μέχρι να γίνει fetch του επίσημου detail resource.</p>
    </section>
  </main>
  <div id="busyOverlay" class="busyOverlay" aria-live="polite" aria-hidden="true">
    <div class="busyPanel">
      <div class="radarPulse"><span></span></div>
      <h3 id="busyTitle">Περιμένετε όσο συλλέγουμε όλα τα δεδομένα</h3>
      <p id="busyText">Επικοινωνούμε με τις επίσημες πηγές και οργανώνουμε τα αρχεία.</p>
    </div>
  </div>
  <script src="/app.js"></script>
</body>
</html>
"""


STYLES_CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6f8;
  --panel: #ffffff;
  --line: #d9dde5;
  --text: #1c2430;
  --muted: #647084;
  --accent: #0f766e;
  --accent-dark: #115e59;
  --soft: #e8f3f1;
  --warn: #9a5b10;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  display: grid;
  grid-template-columns: 248px 1fr;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: Segoe UI, system-ui, -apple-system, sans-serif;
  font-size: 14px;
}
.sidebar {
  background: #1f2933;
  color: white;
  padding: 20px 14px;
}
.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 4px 6px 22px;
}
.mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid #8cbdb6;
  color: #b8e7df;
  font-weight: 700;
}
h1, h2, p { margin: 0; }
h1 { font-size: 17px; }
h2 { font-size: 26px; letter-spacing: 0; }
.brand p, header p, .note, .mutedLine { color: var(--muted); }
.eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
  margin-bottom: 4px;
}
nav { display: grid; gap: 6px; }
button, .button {
  border: 0;
  border-radius: 6px;
  background: var(--accent);
  color: white;
  min-height: 38px;
  padding: 0 14px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: inline-grid;
  place-items: center;
}
button:hover, .button:hover { background: var(--accent-dark); }
button:disabled { opacity: .55; cursor: wait; }
.secondary { background: #edf1f5; color: #23303f; border: 1px solid var(--line); }
.secondary:hover { background: #e1e7ee; }
.danger { background: #b91c1c; color: white; }
.danger:hover { background: #991b1b; }
.nav {
  justify-content: start;
  background: transparent;
  color: #dce6ef;
  border: 1px solid transparent;
}
.nav.active { background: #31404f; border-color: #4c6174; }
main { padding: 22px; min-width: 0; }
.topbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 18px;
}
.view { display: none; }
.view.active { display: block; }
.searchBand {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto;
  gap: 14px;
  align-items: start;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 14px;
}
.searchBand h3 {
  font-size: 20px;
  margin-bottom: 6px;
}
.switchLine {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--text);
  background: #f8fafc;
  font-size: 13px;
}
.switchLine input {
  min-width: 18px;
  width: 18px;
  height: 18px;
}
.inlineSwitch {
  min-height: 38px;
  margin: 0;
}
.inlineToolbar {
  grid-column: 1 / -1;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
  padding: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin-bottom: 14px;
}
.toolbar.compact { margin-top: -4px; }
label { display: grid; gap: 6px; color: var(--muted); font-size: 12px; font-weight: 700; }
input, select {
  min-height: 38px;
  min-width: 180px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0 10px;
  font: inherit;
  color: var(--text);
  background: white;
}
textarea {
  min-height: 128px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  font: inherit;
  color: var(--text);
  background: white;
  resize: vertical;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.metrics div {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.metrics span { display: block; font-size: 24px; font-weight: 750; }
.metrics small { color: var(--muted); }
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 14px;
  align-items: start;
}
.tableWrap {
  overflow: auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.tenderTable { table-layout: fixed; }
table { width: 100%; border-collapse: collapse; min-width: 1060px; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { font-size: 12px; color: var(--muted); background: #f1f4f7; }
.tenderTable tbody tr {
  cursor: pointer;
}
.tenderTable tbody tr:hover {
  background: #f8fafc;
}
.tenderTable tbody tr.selectedRow {
  background: #e8f3f1;
  box-shadow: inset 3px 0 0 var(--accent);
}
td:first-child { font-weight: 700; white-space: nowrap; }
td:nth-child(2) { white-space: nowrap; color: var(--muted); font-weight: 700; }
.tenderTable td:nth-child(3) { white-space: normal; }
.tenderTitle {
  max-width: 360px;
  white-space: normal;
  font-weight: 750;
}
.authorityCell {
  max-width: 300px;
  white-space: normal;
  color: #334155;
}
.deadlineCell, .budgetCell {
  white-space: nowrap;
}
.actionStack {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.tinyButton {
  min-height: 32px;
  padding: 0 10px;
  font-size: 12px;
}
.pill {
  display: inline-block;
  margin-top: 6px;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--soft);
  color: var(--accent-dark);
  font-size: 11px;
  font-weight: 800;
}
.previewPane {
  position: sticky;
  top: 16px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  min-height: 440px;
  overflow: hidden;
}
.previewHeader {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
  padding: 14px;
  border-bottom: 1px solid var(--line);
  background: #f8fafc;
}
.iconLink {
  display: inline-grid;
  place-items: center;
  min-height: 32px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid var(--line);
  color: var(--accent-dark);
  text-decoration: none;
  font-weight: 800;
}
.previewBody {
  display: grid;
  gap: 10px;
  padding: 14px;
}
.docItem {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  background: #ffffff;
}
.docItem h4 {
  margin: 0 0 4px;
  font-size: 14px;
}
.docItem p {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}
.docActions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.commandLog {
  margin-top: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.commandLog summary {
  cursor: pointer;
  padding: 12px 14px;
  color: var(--muted);
  font-weight: 800;
}
.emptyState {
  color: var(--muted);
  padding: 14px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  background: #fbfcfd;
}
pre {
  margin: 0;
  min-height: 320px;
  max-height: 520px;
  overflow: auto;
  background: #151b22;
  color: #dce6ef;
  border-radius: 8px;
  padding: 14px;
  white-space: pre-wrap;
}
.note {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.rulesGrid {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  gap: 14px;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.panelHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
h3 {
  margin: 0;
  font-size: 16px;
}
.ruleList {
  display: grid;
  gap: 8px;
}
.ruleItem {
  width: 100%;
  min-height: 54px;
  justify-content: start;
  text-align: left;
  background: #f5f7fa;
  color: var(--text);
  border: 1px solid var(--line);
}
.ruleItem.active {
  background: #dcefeb;
  border-color: #8ac1b8;
}
.ruleItem small {
  color: var(--muted);
  font-weight: 600;
}
.editorGrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 12px;
}
.editorGrid .wide {
  grid-column: 1 / -1;
}
.inlineControls {
  display: grid;
  grid-template-columns: 92px minmax(120px, 1fr);
  gap: 8px;
}
.inlineControls select,
.inlineControls input {
  min-width: 0;
}
.editorActions {
  margin: 14px 0 0;
}
.noteText {
  color: var(--muted);
  font-size: 13px;
}
.busyOverlay {
  position: fixed;
  inset: 0;
  display: none;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, .48);
  z-index: 20;
}
.busyOverlay.active {
  display: grid;
}
.busyPanel {
  width: min(420px, 100%);
  border-radius: 8px;
  border: 1px solid rgba(184, 231, 223, .55);
  background: #101820;
  color: #edf7f5;
  padding: 24px;
  text-align: center;
  box-shadow: 0 22px 70px rgba(0, 0, 0, .28);
}
.busyPanel h3 {
  font-size: 18px;
  margin: 12px 0 6px;
}
.busyPanel p {
  color: #a8b6c5;
  line-height: 1.45;
}
.radarPulse {
  position: relative;
  width: 88px;
  height: 88px;
  margin: 0 auto;
  border: 1px solid rgba(140, 189, 182, .5);
  border-radius: 50%;
  background:
    radial-gradient(circle at center, rgba(15, 118, 110, .9) 0 5px, transparent 6px),
    repeating-radial-gradient(circle at center, rgba(184, 231, 223, .12) 0 1px, transparent 1px 18px);
  overflow: hidden;
}
.radarPulse::before {
  content: "";
  position: absolute;
  inset: 50% 50% 0 50%;
  width: 44px;
  height: 44px;
  background: linear-gradient(45deg, rgba(45, 212, 191, .85), transparent 62%);
  transform-origin: 0 0;
  animation: sweep 1.45s linear infinite;
}
.radarPulse span {
  position: absolute;
  inset: 20px;
  border: 1px solid rgba(45, 212, 191, .45);
  border-radius: 50%;
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes sweep {
  to { transform: rotate(360deg); }
}
@keyframes pulse {
  50% { transform: scale(1.28); opacity: .45; }
}
@media (max-width: 820px) {
  body { grid-template-columns: 1fr; }
  .sidebar { position: static; }
  nav { grid-template-columns: repeat(3, 1fr); }
  main { padding: 14px; }
  .searchBand,
  .workspace {
    grid-template-columns: 1fr;
  }
  .metrics { grid-template-columns: 1fr; }
  .rulesGrid,
  .editorGrid {
    grid-template-columns: 1fr;
  }
  .editorGrid .wide {
    grid-column: auto;
  }
}
"""


APP_JS = """
const state = {
  selected: null,
  dashboard: null,
  profiles: [],
  evaluationProfiles: [],
  documentTypes: [],
  ruleProfilePath: null,
  evaluationConfig: null,
  selectedRuleId: null,
};
const $ = (id) => document.getElementById(id);

document.querySelectorAll('.nav').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
    button.classList.add('active');
    $(button.dataset.view).classList.add('active');
  });
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function splitList(value) {
  return String(value || '')
    .split(/[,\\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function setBusy(isBusy, text = 'Έτοιμο') {
  $('statusText').textContent = text;
  document.querySelectorAll('button').forEach((button) => { button.disabled = isBusy; });
  $('busyOverlay').classList.toggle('active', isBusy);
  $('busyOverlay').setAttribute('aria-hidden', isBusy ? 'false' : 'true');
  $('busyTitle').textContent = isBusy ? 'Περιμένετε όσο συλλέγουμε όλα τα δεδομένα' : 'Έτοιμο';
  $('busyText').textContent = isBusy
    ? text
    : 'Επικοινωνούμε με τις επίσημες πηγές και οργανώνουμε τα αρχεία.';
}

async function refresh() {
  const status = await api('/api/status');
  state.profiles = status.profiles || [];
  state.evaluationProfiles = status.evaluation_profiles || [];
  state.documentTypes = status.document_types || [];
  fillSelect('profileSelect', state.profiles);
  fillSelect('evaluationProfileSelect', state.evaluationProfiles);
  fillSelect('ruleProfileSelect', state.evaluationProfiles);
  await loadDashboard();
  if (!state.evaluationConfig && $('ruleProfileSelect').value) {
    await loadRules();
  }
}

function fillSelect(id, values) {
  const select = $(id);
  select.innerHTML = '';
  for (const value of values) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value.split('/').pop();
    select.appendChild(option);
  }
}

async function loadDashboard() {
  const scope = $('allGreeceToggle').checked ? 'all' : 'focus';
  const sort = $('sortSelect').value || 'deadline_asc';
  const payload = await api(`/api/dashboard?scope=${scope}&sort=${sort}`);
  state.dashboard = payload;
  renderDashboard(payload);
}

function renderDashboard(payload) {
  $('visibleTenderCount').textContent = payload.summary.visible || 0;
  $('focusTenderCount').textContent = payload.summary.focus_matches || 0;
  const municipalityText = (payload.profile.municipalities || []).join(', ');
  $('scopeText').textContent = payload.scope === 'all'
    ? 'Προβολή όλων των γνωστών/discovered έργων. Η πληρότητα παραμένει μετρήσιμη, όχι δεδομένη.'
    : `Προεπιλογή τοπικού ενδιαφέροντος: ${municipalityText}`;
  renderDiscoverySafety(payload.discovery_run);
  const rows = $('tenderRows');
  rows.innerHTML = '';
  if (!payload.tenders.length) {
    rows.innerHTML = '<tr><td colspan="7" class="emptyState">Δεν υπάρχουν ακόμα έργα για αυτό το φίλτρο. Δοκίμασε νέα αναζήτηση ΕΣΗΔΗΣ ή ενεργοποίησε όλη την Ελλάδα.</td></tr>';
    resetPreview();
    return;
  }
  for (const tender of payload.tenders) {
    const rowKey = tender.row_key || tender.eshidis_id || tender.display_id || '';
    const isEshidis = Boolean(tender.supports_eshidis_actions);
    const isKimdis = Boolean(tender.supports_kimdis_actions);
    const isAuthority = Boolean(tender.supports_authority_actions);
    const linkedIds = tender.linked_eshidis_ids || [];
    const aiIds = tender.ai_triage?.eshidis_id_candidates || [];
    const preferredEshidis = tender.eshidis_id || linkedIds[0] || aiIds[0] || '';
    const sourceIdentifier = isAuthority ? rowKey : (tender.official_id || tender.eshidis_id || tender.display_id || '');
    const fetchIdentifier = preferredEshidis || sourceIdentifier;
    const linkLabel = preferredEshidis ? 'ΕΣΗΔΗΣ' : (tender.source_label === 'ΚΗΜΔΗΣ' ? 'ΚΗΜΔΗΣ' : (tender.source_label === 'Φορέας' ? 'Φορέας' : 'ΕΣΗΔΗΣ'));
    const officialHref = preferredEshidis
      ? `https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/${encodeURIComponent(preferredEshidis)}`
      : (tender.official_url || tender.attachment_url || '#');
    const linkedText = (tender.linked_eshidis_ids || []).length
      ? `<span class="pill">ΕΣΗΔΗΣ ${escapeHtml((tender.linked_eshidis_ids || []).join(', '))}</span>`
      : '';
    const aiText = tender.ai_triage?.decision
      ? `<span class="pill">${escapeHtml(tender.ai_triage.decision)}</span>`
      : '';
    const zipUrl = `/api/document-zip?identifier=${encodeURIComponent(fetchIdentifier)}`;
    const tr = document.createElement('tr');
    tr.dataset.key = rowKey;
    if (state.selected === rowKey) tr.classList.add('selectedRow');
    tr.innerHTML = `
      <td><strong>${escapeHtml(tender.display_id || tender.eshidis_id || '')}</strong></td>
      <td>${escapeHtml(tender.source_label || '')}</td>
      <td class="tenderTitle">${escapeHtml(tender.title || '')}${tender.interest_reason ? `<span class="pill">${escapeHtml(tender.interest_reason)}</span>` : ''}${linkedText}${aiText}</td>
      <td class="authorityCell">${escapeHtml(tender.authority_name || '')}</td>
      <td class="budgetCell">${escapeHtml(tender.budget_display || '')}</td>
      <td class="deadlineCell">${escapeHtml(tender.deadline_display || '')}</td>
      <td>
        <div class="actionStack">
          <a class="button secondary tinyButton" href="${escapeHtml(officialHref)}" target="_blank" rel="noreferrer">${linkLabel}</a>
          ${(isEshidis || isKimdis || isAuthority || preferredEshidis) ? `<button class="tinyButton fetchTender" data-key="${escapeHtml(rowKey)}" data-id="${escapeHtml(fetchIdentifier)}">Fetch</button>` : ''}
          ${(isEshidis || isKimdis || tender.has_local_documents || preferredEshidis) ? `<a class="button secondary tinyButton" href="${escapeHtml(zipUrl)}" target="_blank" rel="noreferrer">ZIP</a>` : ''}
          <button class="tinyButton danger dismissTender" data-key="${escapeHtml(rowKey)}">Δεν με ενδιαφέρει</button>
        </div>
      </td>
    `;
    rows.appendChild(tr);
  }
  document.querySelectorAll('#tenderRows tr[data-key]').forEach((row) => {
    row.addEventListener('click', () => selectTender(row.dataset.key, false));
  });
  document.querySelectorAll('.fetchTender').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      fetchTenderDocuments(button.dataset.key, button.dataset.id);
    });
  });
  document.querySelectorAll('.dismissTender').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      dismissTender(button.dataset.key);
    });
  });
  document.querySelectorAll('#tenderRows a').forEach((link) => {
    link.addEventListener('click', (event) => event.stopPropagation());
  });
  if (!state.selected || !payload.tenders.some((item) => (item.row_key || item.eshidis_id) === state.selected)) {
    selectTender(payload.tenders[0].row_key || payload.tenders[0].eshidis_id, false);
  }
}

function renderDiscoverySafety(run) {
  if (!run) {
    $('discoverySafetyText').textContent = 'Δεν υπάρχει ακόμα καταγεγραμμένο discovery watermark σε αυτό το runtime.';
    return;
  }
  const depth = run.depth || {};
  const watermark = run.watermark || {};
  const status = run.success
    ? 'τελευταίο run πλήρες'
    : (run.source_success ? 'τελευταίο run χρειάζεται βαθύτερο backfill' : 'τελευταίο run με μερική αποτυχία πηγής');
  const mode = run.mode === 'backfill' ? 'backfill' : 'bounded';
  const complete = watermark.complete ? 'το προηγούμενο παράθυρο καλύφθηκε ή εξαντλήθηκε πηγή' : 'χρειάζεται βαθύτερο backfill';
  $('discoverySafetyText').textContent = `${status} · ${mode} · ΕΣΗΔΗΣ ${depth.eshidis_limit || '-'} · ΚΗΜΔΗΣ ${depth.kimdis_pages_per_family || '-'} σελίδες · ${complete}`;
}

function resetPreview() {
  $('previewTitle').textContent = 'Διάλεξε έργο';
  $('officialLink').removeAttribute('href');
  $('previewBody').innerHTML = '<p class="mutedLine">Εδώ θα εμφανιστούν η διακήρυξη, η τεχνική περιγραφή και ο προϋπολογισμός όταν υπάρχουν κατεβασμένα ή γνωστά συνημμένα.</p>';
}

async function selectTender(eshidisId, downloadFirst) {
  if (!eshidisId) return;
  state.selected = eshidisId;
  highlightSelectedRow();
  const tender = (state.dashboard?.tenders || []).find((item) => (item.row_key || item.eshidis_id) === eshidisId) || {};
  const supportsEshidis = Boolean(tender.supports_eshidis_actions);
  const supportsKimdis = Boolean(tender.supports_kimdis_actions);
  const supportsAuthority = Boolean(tender.supports_authority_actions);
  const actualEshidisId = tender.eshidis_id || '';
  const preferredEshidis = actualEshidisId || (tender.linked_eshidis_ids || [])[0] || (tender.ai_triage?.eshidis_id_candidates || [])[0] || '';
  $('eshidisInput').value = supportsEshidis ? actualEshidisId : '';
  $('kimdisInput').value = supportsKimdis ? (tender.official_id || tender.display_id || '') : '';
  $('previewTitle').textContent = `${tender.display_id || actualEshidisId || eshidisId} · ${tender.title || ''}`;
  $('officialLink').textContent = preferredEshidis ? 'ΕΣΗΔΗΣ' : (tender.source_label === 'ΚΗΜΔΗΣ' ? 'ΚΗΜΔΗΣ' : (tender.source_label === 'Φορέας' ? 'Φορέας' : 'ΕΣΗΔΗΣ'));
  $('officialLink').href = preferredEshidis
    ? `https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/${encodeURIComponent(preferredEshidis)}`
    : (tender.official_url || tender.attachment_url || tender.download_url || '#');
  if (supportsAuthority) {
    await renderAuthorityPreview(tender.row_key || eshidisId);
    return;
  }
  if (supportsKimdis) {
    await renderKimdisPreview(tender.official_id || tender.display_id || eshidisId);
    return;
  }
  if (!supportsEshidis) {
    $('previewBody').innerHTML = `
      <div class="emptyState">
        Η γραμμή είναι ${escapeHtml(tender.status || 'candidate')} από το expanded report.
        Δεν υπάρχει ακόμα τοπικό fetched αρχείο για preview. Άνοιξε το link σε νέα καρτέλα για τα επίσημα στοιχεία της πηγής.
      </div>
    `;
    return;
  }
  if (downloadFirst) {
    await runAction('/api/download-all', { eshidis_id: actualEshidisId }, `Downloading files for ${actualEshidisId}...`);
    await loadDashboard();
  }
  await renderPreview(actualEshidisId);
}

function highlightSelectedRow() {
  document.querySelectorAll('#tenderRows tr[data-key]').forEach((row) => {
    row.classList.toggle('selectedRow', row.dataset.key === state.selected);
  });
}

async function fetchTenderDocuments(rowKey, identifier) {
  if (!identifier) return;
  if (rowKey) state.selected = rowKey;
  await runAction(
    '/api/fetch-selected',
    { identifier },
    `Συλλογή επίσημων εγγράφων για ${identifier}...`
  );
  await loadDashboard();
  const tender = (state.dashboard?.tenders || []).find((item) => (item.row_key || item.eshidis_id) === rowKey) || {};
  if (isKimdisCode(identifier)) {
    await renderKimdisPreview(identifier);
  } else if (String(identifier || '').startsWith('AUTHORITY:')) {
    await renderAuthorityPreview(identifier);
  } else {
    await renderPreview(identifier);
  }
  if (tender.title) {
    $('previewTitle').textContent = `${tender.display_id || identifier} · ${tender.title}`;
  }
}

function isKimdisCode(value) {
  return /^\\d{2}PROC\\d{9}$/.test(String(value || '').trim());
}

async function dismissTender(rowKey) {
  if (!rowKey) return;
  await api('/api/dismiss-tender', { method: 'POST', body: JSON.stringify({ row_key: rowKey }) });
  if (state.selected === rowKey) {
    state.selected = null;
    resetPreview();
  }
  await loadDashboard();
}

async function renderAuthorityPreview(rowKey) {
  const payload = await api(`/api/authority-document-preview?row_key=${encodeURIComponent(rowKey)}`);
  const docs = payload.documents || [];
  if (!docs.length) {
    $('previewBody').innerHTML = '<div class="emptyState">Υπάρχουν links εγγράφων στη σελίδα του φορέα. Πάτα Fetch για να κατέβουν τοπικά και μετά ZIP.</div>';
    return;
  }
  $('previewBody').innerHTML = docs.map((doc) => `
    <article class="docItem">
      <h4>${escapeHtml(doc.label)}${doc.available ? '' : ' · δεν έχει κατέβει'}</h4>
      <p>${escapeHtml(doc.name || '')}</p>
      <div class="docActions">
        ${doc.view_url ? `<a class="button tinyButton" href="${escapeHtml(doc.view_url)}" target="_blank" rel="noreferrer">Open</a>` : ''}
      </div>
    </article>
  `).join('');
}

async function renderKimdisPreview(officialId) {
  const payload = await api(`/api/kimdis-document-preview?official_id=${encodeURIComponent(officialId)}`);
  const docs = payload.documents || [];
  const linkedIds = payload.linked_eshidis_ids || [];
  const linkedFileCount = Number(payload.linked_eshidis_file_count || 0);
  if (!docs.length) {
    $('previewBody').innerHTML = '<div class="emptyState">Δεν υπάρχει ακόμα structured ΚΗΜΔΗΣ preview για αυτό το ΑΔΑΜ.</div>';
    return;
  }
  const linkedBlock = linkedIds.length
    ? `<div class="docItem linkedBox"><h4>Σύνδεση με ΕΣΗΔΗΣ</h4><p>Βρέθηκε Α/Α ΕΣΗΔΗΣ ${escapeHtml(linkedIds.join(', '))}. ${linkedFileCount ? `Υπάρχουν ήδη ${linkedFileCount} επίσημα αρχεία ΕΣΗΔΗΣ διαθέσιμα για zip.` : 'Το Fetch αυτής της γραμμής θα επιχειρήσει να κατεβάσει και τον επίσημο φάκελο ΕΣΗΔΗΣ.'}</p></div>`
    : '';
  $('previewBody').innerHTML = linkedBlock + docs.map((doc) => `
    <article class="docItem">
      <h4>${escapeHtml(doc.label)}${doc.available ? '' : ' · δεν έχει κατέβει'}</h4>
      <p>${escapeHtml(doc.name || '')}</p>
      ${doc.text_sample ? `<p>${escapeHtml(String(doc.text_sample).slice(0, 220))}</p>` : ''}
      ${doc.evidence_status ? `<p class="noteText">${escapeHtml(doc.evidence_status)}${doc.authority_match ? ` · ${escapeHtml(doc.authority_match)}` : ''}</p>` : ''}
      <div class="docActions">
        ${doc.view_url ? `<a class="button tinyButton" href="${escapeHtml(doc.view_url)}" target="_blank" rel="noreferrer">Open</a>` : ''}
      </div>
    </article>
  `).join('');
}

async function renderPreview(eshidisId) {
  const payload = await api(`/api/document-preview?eshidis_id=${encodeURIComponent(eshidisId)}`);
  const docs = payload.documents || [];
  if (!docs.length) {
    $('previewBody').innerHTML = '<div class="emptyState">Δεν υπάρχουν ακόμα συνημμένα στη βάση για αυτό το έργο. Πάτα Fetch official detail και μετά Download files.</div>';
    return;
  }
  $('previewBody').innerHTML = docs.map((doc) => `
    <article class="docItem">
      <h4>${escapeHtml(doc.label)}${doc.available ? '' : ' · δεν έχει κατέβει'}</h4>
      <p>${escapeHtml(doc.name || '')}</p>
      ${doc.text_sample ? `<p>${escapeHtml(String(doc.text_sample).slice(0, 220))}</p>` : ''}
      <div class="docActions">
        ${doc.view_url ? `<a class="button tinyButton" href="${escapeHtml(doc.view_url)}" target="_blank" rel="noreferrer">Open</a>` : ''}
      </div>
    </article>
  `).join('');
}

async function runAction(path, body, label) {
  setBusy(true, label);
  $('commandOutput').textContent = `${label}\\n`;
  try {
    const initial = await api(path, { method: 'POST', body: JSON.stringify(body || {}) });
    const result = initial.job_id ? await pollJob(initial.job_id, label) : initial;
    $('commandOutput').textContent = JSON.stringify(result, null, 2);
    const finalResult = result.result || result;
    $('statusText').textContent = finalResult.ok === false || result.status === 'failed' ? 'Τελείωσε με σφάλματα' : 'Ολοκληρώθηκε';
    await loadDashboard();
  } catch (error) {
    $('commandOutput').textContent = String(error);
    $('statusText').textContent = 'Σφάλμα';
  } finally {
    setBusy(false, $('statusText').textContent);
  }
}

async function pollJob(jobId, label) {
  let attempts = 0;
  while (true) {
    await sleep(5000);
    attempts += 1;
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    $('statusText').textContent = `${label} · έλεγχος ${attempts}`;
    $('busyText').textContent = `${label} · ελέγχουμε κάθε 5 δευτερόλεπτα`;
    $('commandOutput').textContent = JSON.stringify(job, null, 2);
    if (job.status === 'completed' || job.status === 'failed') {
      return job;
    }
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function selectedId() {
  return $('eshidisInput').value.trim();
}

function selectedKimdisId() {
  return $('kimdisInput').value.trim();
}

async function previewSelectedKimdis() {
  const officialId = selectedKimdisId();
  if (!officialId) return;
  state.selected = `KIMDIS:${officialId}`;
  $('previewTitle').textContent = officialId;
  $('officialLink').textContent = 'ΚΗΜΔΗΣ';
  $('officialLink').href = `https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice/attachment/${encodeURIComponent(officialId)}`;
  await renderKimdisPreview(officialId);
}

async function loadRules() {
  const path = $('ruleProfileSelect').value || $('evaluationProfileSelect').value;
  if (!path) return;
  const result = await api(`/api/evaluation-profile?path=${encodeURIComponent(path)}`);
  state.ruleProfilePath = result.path;
  state.evaluationConfig = result.data;
  state.selectedRuleId = (result.data.rules[0] || {}).id || null;
  renderRules();
  fillRuleForm(currentRule());
  $('rulesStatus').textContent = `Loaded ${result.data.rules.length} rules.`;
}

function currentRule() {
  const rules = ((state.evaluationConfig || {}).rules || []);
  return rules.find((rule) => rule.id === state.selectedRuleId) || null;
}

function renderRules() {
  const list = $('ruleList');
  list.innerHTML = '';
  const rules = ((state.evaluationConfig || {}).rules || []);
  if (!rules.length) {
    list.innerHTML = '<p class="noteText">No rules yet.</p>';
    return;
  }
  for (const rule of rules) {
    const button = document.createElement('button');
    button.className = `ruleItem ${rule.id === state.selectedRuleId ? 'active' : ''}`;
    button.dataset.id = rule.id;
    button.innerHTML = `
      <span>${escapeHtml(rule.label || rule.id)}</span>
      <small>${escapeHtml(rule.id)} · +${escapeHtml(rule.score || 0)} · ${escapeHtml(rule.severity || 'info')}</small>
    `;
    button.addEventListener('click', () => {
      state.selectedRuleId = rule.id;
      renderRules();
      fillRuleForm(rule);
    });
    list.appendChild(button);
  }
}

function fillRuleForm(rule) {
  $('ruleIdInput').value = rule?.id || '';
  $('ruleLabelInput').value = rule?.label || '';
  $('ruleSeverityInput').value = rule?.severity || 'info';
  $('ruleScoreInput').value = rule?.score ?? 1;
  $('ruleDocumentTypesInput').value = (rule?.document_types || []).join(', ');
  $('rulePhrasesInput').value = (rule?.phrases || []).join('\\n');
  $('ruleOperatorInput').value = rule?.numeric?.operator || '';
  $('ruleThresholdInput').value = rule?.numeric?.threshold ?? '';
}

function ruleFromForm() {
  const id = $('ruleIdInput').value.trim();
  const phrases = splitList($('rulePhrasesInput').value);
  if (!id) throw new Error('Rule id is required.');
  if (!phrases.length) throw new Error('At least one phrase is required.');
  const rule = {
    id,
    label: $('ruleLabelInput').value.trim() || id,
    severity: $('ruleSeverityInput').value,
    score: Number($('ruleScoreInput').value || 1),
    document_types: splitList($('ruleDocumentTypesInput').value),
    phrases,
  };
  const operator = $('ruleOperatorInput').value;
  const threshold = $('ruleThresholdInput').value;
  if (operator && threshold !== '') {
    rule.numeric = { operator, threshold: Number(threshold) };
  }
  return rule;
}

function applyRule() {
  if (!state.evaluationConfig) {
    state.evaluationConfig = { profile: { id: 'public_works_dynamic', name: 'Dynamic public works evaluation', description: '' }, rules: [] };
  }
  const rule = ruleFromForm();
  const rules = state.evaluationConfig.rules || [];
  const index = rules.findIndex((item) => item.id === state.selectedRuleId || item.id === rule.id);
  if (index >= 0) {
    rules[index] = rule;
  } else {
    rules.push(rule);
  }
  state.evaluationConfig.rules = rules;
  state.selectedRuleId = rule.id;
  renderRules();
  $('rulesStatus').textContent = 'Rule applied locally. Press Save Rules to write it.';
}

async function saveRules() {
  applyRule();
  const path = state.ruleProfilePath || $('ruleProfileSelect').value;
  const result = await api('/api/evaluation-profile', {
    method: 'POST',
    body: JSON.stringify({ path, data: state.evaluationConfig }),
  });
  state.evaluationConfig = result.data;
  state.ruleProfilePath = result.path;
  renderRules();
  $('rulesStatus').textContent = `Saved ${result.data.rules.length} rules.`;
}

function newRule() {
  state.selectedRuleId = null;
  fillRuleForm({
    id: `rule_${Date.now()}`,
    label: '',
    severity: 'info',
    score: 1,
    document_types: [],
    phrases: [],
  });
  renderRules();
  $('rulesStatus').textContent = 'Fill the new rule and press Apply Rule.';
}

function deleteRule() {
  if (!state.evaluationConfig || !state.selectedRuleId) return;
  state.evaluationConfig.rules = (state.evaluationConfig.rules || []).filter((rule) => rule.id !== state.selectedRuleId);
  state.selectedRuleId = (state.evaluationConfig.rules[0] || {}).id || null;
  renderRules();
  fillRuleForm(currentRule());
  $('rulesStatus').textContent = 'Rule removed locally. Press Save Rules to write it.';
}

$('refreshBtn').addEventListener('click', refresh);
$('allGreeceToggle').addEventListener('change', () => loadDashboard().catch((error) => { $('statusText').textContent = String(error); }));
$('sortSelect').addEventListener('change', () => loadDashboard().catch((error) => { $('statusText').textContent = String(error); }));
$('discoverBtn').addEventListener('click', () => {
  const backfill = $('backfillToggle').checked;
  runAction(
    '/api/discover',
    { limit: $('limitInput').value, backfill },
    backfill ? 'Backfill αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ...' : 'Bounded αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ...'
  );
});
$('fetchBtn').addEventListener('click', () => runAction('/api/fetch-resource', { eshidis_id: selectedId() }, 'Fetching official detail...'));
$('downloadBtn').addEventListener('click', () => runAction('/api/download-all', { eshidis_id: selectedId() }, 'Downloading attachments...'));
$('analyzeBtn').addEventListener('click', () => runAction('/api/analyze', { eshidis_id: selectedId() }, 'Analyzing documents...'));
$('kimdisPreviewBtn').addEventListener('click', () => previewSelectedKimdis().catch((error) => { $('statusText').textContent = String(error); }));
$('kimdisFetchBtn').addEventListener('click', () => runAction('/api/fetch-kimdis-open-proc', {}, 'Fetching KIMDIS attachments...'));
$('searchBtn').addEventListener('click', () => runAction('/api/search', { eshidis_id: selectedId(), profile: $('profileSelect').value }, 'Running search profile...'));
$('evaluateBtn').addEventListener('click', () => runAction('/api/evaluate', { eshidis_id: selectedId(), profile: $('evaluationProfileSelect').value }, 'Running evaluation rules...'));
$('loadRulesBtn').addEventListener('click', () => loadRules().catch((error) => { $('rulesStatus').textContent = String(error); }));
$('saveRulesBtn').addEventListener('click', () => saveRules().catch((error) => { $('rulesStatus').textContent = String(error); }));
$('applyRuleBtn').addEventListener('click', () => {
  try { applyRule(); } catch (error) { $('rulesStatus').textContent = String(error); }
});
$('newRuleBtn').addEventListener('click', newRule);
$('deleteRuleBtn').addEventListener('click', deleteRule);

refresh().catch((error) => { $('statusText').textContent = String(error); });
"""


if __name__ == "__main__":
    raise SystemExit(main())
