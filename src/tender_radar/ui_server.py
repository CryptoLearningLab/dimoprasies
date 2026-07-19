from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import io
import json
import mimetypes
import os
import re
import secrets
import smtplib
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
from urllib.parse import parse_qs, quote, urlencode, unquote, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from tender_radar import __version__
from tender_radar.config import load_config
from tender_radar.db import (
    create_admin_invite,
    delete_stale_verified_tender_links,
    dismiss_tender as dismiss_tender_in_db,
    get_admin_invite,
    get_admin_user,
    get_source_document,
    get_source_state,
    ignored_tender_keys as ignored_tender_keys_from_db,
    list_admin_users,
    list_source_documents,
    list_tender_dismissals,
    list_source_states,
    list_verified_tender_links,
    mark_admin_invite_used,
    notification_already_sent,
    record_admin_user_login,
    record_source_run,
    record_notification_sent,
    remove_tender_dismissal,
    triage_overrides_by_key as db_triage_overrides_by_key,
    upsert_admin_user,
    upsert_triage_override,
    upsert_source_document,
    upsert_source_state,
    upsert_verified_tender_link,
)
from tender_radar.discovery_watermark import (
    append_discovery_run,
    build_discovery_run_record,
    latest_discovery_run,
    latest_successful_discovery_run,
    utc_now_iso,
)
from tender_radar.documents import analyze_document
from tender_radar.evaluation import normalize_evaluation_config, save_evaluation_config
from tender_radar.ai_triage import AI_TRIAGE_PROMPT_VERSION
from tender_radar.sources.expanded_report import classify_public_works_candidate_dict
from tender_radar.sources.kimdis_connected_acts import fetch_kimdis_connected_acts
from tender_radar.sources.kimdis_fetch import extract_eshidis_ids_from_text


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_ESHIDIS_DISCOVERY_LIMIT = 100
DEFAULT_KIMDIS_DISCOVERY_PAGES = 20
DEFAULT_SCHEDULED_AUTO_FETCH_SECONDS = 20
DEFAULT_AUTHORITY_LIMIT_PER_SOURCE = 10
MAX_BACKFILL_ESHIDIS_LIMIT = 500
MAX_BACKFILL_KIMDIS_PAGES = 80
COMMAND_LOCK = threading.Lock()
ENRICHMENT_LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}
ADMIN_SESSIONS_LOCK = threading.Lock()
ADMIN_SESSIONS: dict[str, dict[str, str]] = {}
ADMIN_LOGIN_CODES_LOCK = threading.Lock()
ADMIN_LOGIN_CODES: dict[str, dict[str, Any]] = {}


def runtime_db_path() -> Path:
    return REPO_ROOT / "data/tender_radar.sqlite"


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
        if parsed.path in {"/", "/password-setup"}:
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
        if parsed.path == "/api/auth/status":
            self._send_json(auth_status_payload(self._admin_session()))
            return
        if parsed.path.startswith("/api/admin/"):
            pass
        elif parsed.path.startswith("/api/") and not self._any_authenticated():
            self._send_json({"ok": False, "authenticated": False, "error": "Login required."}, status=401)
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
        if parsed.path == "/api/source-polling":
            self._send_json(source_polling_payload())
            return
        if parsed.path == "/api/admin/audit":
            if not self._admin_authenticated():
                self._send_json({"ok": False, "authenticated": False, **admin_status_payload()}, status=401)
                return
            self._send_json(admin_audit_payload())
            return
        if parsed.path == "/api/admin/users":
            session = self._admin_session()
            if not session or session.get("role") != "admin":
                self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                return
            self._send_json(admin_users_payload())
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
            if parsed.path == "/api/auth/login":
                self._auth_login(payload)
                return
            if parsed.path == "/api/auth/logout":
                self._admin_logout()
                return
            if parsed.path == "/api/admin/set-password":
                self._admin_set_password(payload)
                return
            if parsed.path.startswith("/api/admin/"):
                pass
            elif parsed.path.startswith("/api/") and not self._any_authenticated():
                self._send_json({"ok": False, "authenticated": False, "error": "Login required."}, status=401)
                return
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
            if parsed.path == "/api/enrich-candidates":
                scope = str(payload.get("scope") or "focus")
                limit = int(payload.get("limit") or 50)
                self._send_json(start_job("enrich-candidates", run_candidate_enrichment, scope=scope, limit=limit), status=202)
                return
            if parsed.path == "/api/ai-triage":
                scope = str(payload.get("scope") or "focus")
                sort = str(payload.get("sort") or "deadline_asc")
                batch_size = int(payload.get("batch_size") or 20)
                self._send_json(
                    start_job("ai-triage", run_ai_triage, scope=scope, sort=sort, batch_size=batch_size),
                    status=202,
                )
                return
            if parsed.path == "/api/email-alerts":
                scope = str(payload.get("scope") or "focus")
                sort = str(payload.get("sort") or "deadline_asc")
                dry_run = bool(payload.get("dry_run", False))
                recipient = str(payload.get("recipient") or "").strip() or None
                self._send_json(start_job("email-alerts", run_email_alerts, scope=scope, sort=sort, recipient=recipient, dry_run=dry_run), status=202)
                return
            if parsed.path == "/api/dismiss-tender":
                row_key = require_row_key(payload)
                self._send_json(dismiss_tender(row_key))
                return
            if parsed.path == "/api/admin/login":
                self._admin_login(payload)
                return
            if parsed.path == "/api/admin/request-code":
                self._send_json(request_admin_login_code(payload))
                return
            if parsed.path == "/api/admin/verify-code":
                self._admin_verify_code(payload)
                return
            if parsed.path == "/api/admin/request-password-setup":
                self._send_json(request_admin_password_setup(payload, base_url=self._public_base_url()))
                return
            if parsed.path == "/api/admin/invite-user":
                session = self._admin_session()
                if not session or session.get("role") != "admin":
                    self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                    return
                self._send_json(invite_admin_user(payload, inviter=session.get("email"), base_url=self._public_base_url()))
                return
            if parsed.path == "/api/admin/logout":
                self._admin_logout()
                return
            if parsed.path == "/api/admin/restore":
                if not self._admin_authenticated():
                    self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                    return
                row_key = require_row_key(payload)
                reason = str(payload.get("reason") or "").strip() or None
                self._send_json(restore_admin_row(row_key=row_key, reason=reason))
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

    def _send_json(self, payload: dict[str, Any], status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _admin_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        email = str(payload.get("email") or admin_login_email() or "").strip().lower()
        submitted = str(payload.get("password") or "")
        if email and verify_admin_user_password(email=email, password=submitted):
            user = get_admin_user(runtime_db_path(), email)
            if not user:
                raise ValueError("Invalid admin user.")
            record_admin_user_login(runtime_db_path(), email)
            self._send_admin_session(email=email, role=user.role)
            return {}
        password = admin_password()
        if not password:
            raise ValueError("Admin password is not configured.")
        if not secrets.compare_digest(submitted, password):
            raise ValueError("Invalid admin password.")
        self._send_admin_session(email=email or "env-admin", role="admin")
        return {}

    def _auth_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        email = str(payload.get("email") or "").strip().lower()
        submitted = str(payload.get("password") or "")
        user = get_admin_user(runtime_db_path(), email) if email else None
        if user and user.enabled and verify_password(submitted, user.password_hash):
            record_admin_user_login(runtime_db_path(), email)
            self._send_admin_session(email=email, role=user.role)
            return {}
        password = admin_password()
        owner_email = admin_login_email() or "env-admin"
        if password and secrets.compare_digest(submitted, password) and (not email or email == owner_email):
            self._send_admin_session(email=email or owner_email, role="admin")
            return {}
        raise ValueError("Invalid email or password.")

    def _admin_verify_code(self, payload: dict[str, Any]) -> dict[str, Any]:
        email = str(payload.get("email") or "").strip().lower()
        code = str(payload.get("code") or "").strip()
        if not verify_admin_login_code(email=email, code=code):
            raise ValueError("Invalid or expired admin code.")
        ensure_owner_admin_user(email)
        record_admin_user_login(runtime_db_path(), email)
        self._send_admin_session(email=email, role="admin")
        return {}

    def _admin_set_password(self, payload: dict[str, Any]) -> dict[str, Any]:
        token = str(payload.get("token") or "").strip()
        password = str(payload.get("password") or "")
        user = complete_admin_password_setup(token=token, password=password)
        record_admin_user_login(runtime_db_path(), user["email"])
        self._send_admin_session(email=str(user["email"]), role=str(user["role"]))
        return {}

    def _send_admin_session(self, *, email: str, role: str) -> None:
        token = secrets.token_urlsafe(32)
        with ADMIN_SESSIONS_LOCK:
            ADMIN_SESSIONS[token] = {"email": email, "role": role}
        body = {"ok": True, "authenticated": True, "admin": admin_status_payload(), "session": {"email": email, "role": role}}
        cookie = f"tr_admin_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200"
        self._send_json(body, extra_headers={"Set-Cookie": cookie})

    def _admin_logout(self) -> dict[str, Any]:
        token = self._admin_session_token()
        if token:
            with ADMIN_SESSIONS_LOCK:
                ADMIN_SESSIONS.pop(token, None)
        body = {"ok": True, "authenticated": False}
        self._send_json(body, extra_headers={"Set-Cookie": "tr_admin_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})
        return {}

    def _public_base_url(self) -> str:
        configured = public_base_url()
        if configured:
            return configured
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or f"{DEFAULT_HOST}:{DEFAULT_PORT}"
        proto = self.headers.get("X-Forwarded-Proto") or ("https" if str(host).endswith(".sslip.io") else "http")
        return f"{proto}://{host}".rstrip("/")

    def _admin_session_token(self) -> str | None:
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)
            if key == "tr_admin_session" and value:
                return value
        return None

    def _admin_authenticated(self) -> bool:
        session = self._admin_session()
        return bool(session and session.get("role") == "admin")

    def _any_authenticated(self) -> bool:
        return bool(self._admin_session())

    def _admin_session(self) -> dict[str, str] | None:
        token = self._admin_session_token()
        if not token:
            return None
        with ADMIN_SESSIONS_LOCK:
            return ADMIN_SESSIONS.get(token)

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
    authority_row = authority_row_by_key(identifier)
    if authority_row:
        authority_result = run_authority_fetch(identifier)
        linked_ids = sorted(
            {
                *authority_linked_eshidis_ids(identifier),
                *(
                    [str(authority_row.get("eshidis_id"))]
                    if str(authority_row.get("eshidis_id") or "").isdigit()
                    else []
                ),
            }
        )
        if not linked_ids:
            return {
                **authority_result,
                "linked_eshidis_ids": [],
                "eshidis_fetch": None,
                "dashboard": dashboard_payload(scope="focus"),
            }
        eshidis_result = run_official_eshidis_fetch(linked_ids)
        return {
            **authority_result,
            "ok": authority_result.get("ok") is not False and eshidis_result.get("ok") is not False,
            "linked_eshidis_ids": linked_ids,
            "eshidis_fetch": eshidis_result,
            "dashboard": eshidis_result.get("dashboard") or dashboard_payload(scope="focus"),
        }
    if is_kimdis_identifier(identifier):
        kimdis_result = run_kimdis_fetch(official_id=identifier)
        linked_ids = kimdis_linked_eshidis_ids(identifier)
        connected_acts_result = None
        if not linked_ids:
            connected_acts_result = run_kimdis_connected_acts_lookup(identifier)
            linked_ids = kimdis_linked_eshidis_ids(identifier)
        if not linked_ids:
            return {
                "ok": kimdis_result.get("ok") is not False,
                "kimdis_fetch": kimdis_result,
                "kimdis_connected_acts": connected_acts_result,
                "linked_eshidis_ids": [],
                "eshidis_fetch": None,
                "dashboard": dashboard_payload(scope="focus"),
            }
        eshidis_result = run_official_eshidis_fetch(linked_ids)
        persist_verified_links_for_selected_fetch(
            source_row_key=f"KIMDIS:{identifier}",
            source_identifier=identifier,
            source_label="ΚΗΜΔΗΣ",
            linked_ids=linked_ids,
            eshidis_fetch=eshidis_result,
        )
        return {
            "ok": kimdis_result.get("ok") is not False and eshidis_result.get("ok") is not False,
            "kimdis_fetch": kimdis_result,
            "kimdis_connected_acts": connected_acts_result,
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


def run_official_eshidis_fetch(eshidis_ids: list[str]) -> dict[str, Any]:
    steps = official_eshidis_fetch_steps(eshidis_ids)
    return run_cli_steps(steps, dashboard_scope="focus") if steps else {"ok": True, "steps": [], "dashboard": dashboard_payload(scope="focus")}


def official_eshidis_fetch_steps(eshidis_ids: list[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for eshidis_id in list(dict.fromkeys(str(value) for value in eshidis_ids if str(value).strip())):
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
    return steps


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
    skipped = 0
    signature = candidate_enrichment_signature(row)
    existing_documents = {str(item.get("attachment_url") or ""): item for item in authority_documents_by_key().get(row_key, [])}
    for index, url in enumerate(urls):
        existing = reusable_source_document(row_key=row_key, document_url=url, source_signature=signature)
        if existing:
            skipped += 1
            documents.append(
                existing_authority_document_payload(
                    row_key=row_key,
                    row=row,
                    url=url,
                    source_document=existing,
                    fallback=existing_documents.get(url),
                )
            )
            continue
        try:
            path, size_bytes = download_authority_document(url, target_dir, index)
            digest = sha256_file(path)
            retrieved_at = utc_now_iso()
            analysis_payload, text_path, linked_eshidis_ids = inspect_authority_document(
                path,
                row=row,
                attachment_url=url,
                index=index,
            )
            document = {
                "row_key": row_key,
                "official_id": row.get("official_id"),
                "title": row.get("title"),
                "source_url": row.get("official_url"),
                "attachment_url": url,
                "local_path": str(path),
                "original_filename": path.name,
                "size_bytes": size_bytes,
                "sha256": digest,
                "retrieved_at": retrieved_at,
                "document_analysis": analysis_payload,
                "text_path": str(text_path) if text_path else None,
                "linked_eshidis_ids": linked_eshidis_ids,
            }
            documents.append(document)
            upsert_source_document(
                runtime_db_path(),
                row_key=row_key,
                document_url=url,
                source_url=str(row.get("official_url") or ""),
                local_path=str(path),
                size_bytes=size_bytes,
                sha256=digest,
                fetched_at=retrieved_at,
                source_signature=signature,
                metadata={
                    "source": "authority",
                    "official_id": row.get("official_id"),
                    "title": row.get("title"),
                    "linked_eshidis_ids": linked_eshidis_ids,
                    "text_path": str(text_path) if text_path else None,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive network boundary
            failures.append({"url": url, "message": str(exc)})
            upsert_source_document(
                runtime_db_path(),
                row_key=row_key,
                document_url=url,
                source_url=str(row.get("official_url") or ""),
                fetch_error=str(exc),
                source_signature=signature,
                metadata={"source": "authority", "official_id": row.get("official_id"), "title": row.get("title")},
            )
    index_payload = write_authority_document_index(row_key, documents)
    return {
        "ok": not failures and bool(documents),
        "row_key": row_key,
        "downloaded": len(documents) - skipped,
        "skipped": skipped,
        "failed": len(failures),
        "failures": failures,
        "linked_eshidis_ids": authority_linked_eshidis_ids(row_key, documents=documents),
        "document_index": index_payload,
        "dashboard": dashboard_payload(scope="focus"),
    }


def reusable_source_document(*, row_key: str, document_url: str, source_signature: str) -> Any | None:
    record = get_source_document(runtime_db_path(), row_key=row_key, document_url=document_url)
    if not record or record.fetch_error:
        return None
    if record.source_signature != source_signature:
        return None
    if not record.local_path or not record.sha256:
        return None
    if not Path(record.local_path).exists():
        return None
    return record


def existing_authority_document_payload(
    *,
    row_key: str,
    row: dict[str, Any],
    url: str,
    source_document: Any,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = fallback or {}
    path = Path(str(source_document.local_path))
    metadata = source_document.metadata or {}
    return {
        "row_key": row_key,
        "official_id": row.get("official_id") or fallback.get("official_id"),
        "title": row.get("title") or fallback.get("title"),
        "source_url": row.get("official_url") or fallback.get("source_url"),
        "attachment_url": url,
        "local_path": str(path),
        "original_filename": path.name,
        "size_bytes": source_document.size_bytes,
        "sha256": source_document.sha256,
        "retrieved_at": source_document.fetched_at,
        "document_analysis": fallback.get("document_analysis"),
        "text_path": metadata.get("text_path") or fallback.get("text_path"),
        "linked_eshidis_ids": metadata.get("linked_eshidis_ids") or fallback.get("linked_eshidis_ids") or [],
        "provenance_status": "REUSED_FROM_SQLITE_SOURCE_DOCUMENT",
    }


def inspect_authority_document(
    path: Path,
    *,
    row: dict[str, Any],
    attachment_url: str,
    index: int,
) -> tuple[dict[str, object] | None, Path | None, list[str]]:
    if path.suffix.lower() == ".zip":
        linked_ids = extract_eshidis_ids_from_text(
            path.name,
            row.get("title"),
            row.get("authority_name"),
            row.get("official_url"),
            attachment_url,
            *authority_zip_entry_names(path),
        )
        return None, None, linked_ids
    analysis = analyze_document(path, original_name=path.name)
    payload = analysis.to_dict()
    full_text = payload.pop("full_text", None)
    text_path = write_authority_text_artifact(str(row.get("row_key") or "authority"), index, full_text)
    linked_ids = extract_eshidis_ids_from_text(
        path.name,
        row.get("title"),
        row.get("authority_name"),
        row.get("official_url"),
        attachment_url,
        full_text,
    )
    return payload, text_path, linked_ids


def authority_zip_entry_names(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return []


def write_authority_text_artifact(row_key: str, index: int, full_text: object) -> Path | None:
    if not isinstance(full_text, str) or not full_text.strip():
        return None
    path = REPO_ROOT / "work/extracted_text/authority" / f"{safe_filename(row_key)}_{index}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(full_text, encoding="utf-8")
    return path


def run_kimdis_fetch(*, official_id: str | None = None) -> dict[str, Any]:
    args = kimdis_fetch_args()
    if official_id:
        official_id = require_kimdis_id({"official_id": official_id})
        args.extend(["--official-id", official_id])
    return run_cli_command(args)


def run_kimdis_connected_acts_lookup(official_id: str) -> dict[str, Any]:
    official_id = require_kimdis_id({"official_id": official_id})
    result = fetch_kimdis_connected_acts(
        official_id,
        download_dir=REPO_ROOT / "work/download_audit/kimdis_connected_acts" / safe_filename(official_id),
        text_dir=REPO_ROOT / "work/extracted_text/kimdis_connected_acts" / safe_filename(official_id),
        timeout_seconds=30,
        allow_insecure_tls=True,
        max_attachments=12,
    ).to_dict()
    report_path = REPO_ROOT / "work/reports" / f"kimdis_connected_acts_{safe_filename(official_id)}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    merge_kimdis_connected_acts_result(official_id, result)
    return {
        "ok": result.get("chain_status") == "FETCHED",
        "official_id": official_id,
        "report_path": str(report_path),
        "summary": {
            "linked_eshidis_ids": len(result.get("linked_eshidis_ids") or []),
            "connected_attachments": len(result.get("attachment_results") or []),
            "errors": len(result.get("errors") or []),
        },
        **result,
    }


def merge_kimdis_connected_acts_result(official_id: str, result: dict[str, Any]) -> None:
    index_path = REPO_ROOT / "work/derived/kimdis_open_proc_documents.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            index = {}
    else:
        index = {}
    documents = index.get("documents") if isinstance(index.get("documents"), list) else []
    target = None
    for document in documents:
        if isinstance(document, dict) and str(document.get("official_id") or "") == official_id:
            target = document
            break
    if target is None:
        target = {
            "source": "KIMDIS",
            "record_type": "PROC",
            "official_id": official_id,
            "candidate_status": "SUBMISSION_OPEN_CANDIDATE",
            "verification_status": "CONNECTED_ACTS_FETCHED_PENDING_DOCUMENT_REVIEW",
        }
        documents.append(target)
    linked_ids = []
    for value in [*(target.get("linked_eshidis_ids") or []), *(result.get("linked_eshidis_ids") or [])]:
        text = str(value or "").strip()
        if text.isdigit() and text not in linked_ids:
            linked_ids.append(text)
    target["linked_eshidis_ids"] = linked_ids
    target["connected_acts"] = {
        "checked_at": result.get("checked_at"),
        "chain_url": result.get("chain_url"),
        "chain_status": result.get("chain_status"),
        "chain": result.get("chain") or {},
        "linked_eshidis_ids": result.get("linked_eshidis_ids") or [],
        "errors": result.get("errors") or [],
        "attachment_results": result.get("attachment_results") or [],
    }
    index["documents"] = documents
    index["generated_at"] = index.get("generated_at") or utc_now_iso()
    index["updated_at"] = utc_now_iso()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def run_ai_triage(*, scope: str = "focus", sort: str = "deadline_asc", batch_size: int = 20) -> dict[str, Any]:
    safe_scope = scope if scope in {"focus", "all"} else "focus"
    safe_sort = sort if sort in {"deadline_asc", "budget_desc"} else "deadline_asc"
    safe_batch_size = max(1, min(int(batch_size), 50))
    result = run_cli_command(
        [
            "sources",
            "ai-triage-report",
            "--scope",
            safe_scope,
            "--sort",
            safe_sort,
            "--batch-size",
            str(safe_batch_size),
            "--timeout",
            "90",
            "--report",
            "work/reports/ai_triage_report.json",
            "--markdown-report",
            "work/reports/ai_triage_report.md",
        ]
    )
    result["dashboard"] = dashboard_payload(scope=safe_scope, sort=safe_sort)
    result["ai_triage_report"] = ai_triage_report_status()
    return result


def run_incremental_ai_triage(*, scope: str = "focus", sort: str = "deadline_asc", batch_size: int = 20) -> dict[str, Any]:
    dashboard = dashboard_payload(scope=scope, sort=sort, apply_triage=False)
    rows = [row for row in dashboard.get("tenders") or [] if isinstance(row, dict)]
    existing_report = load_ai_triage_report_payload()
    existing_rows = [row for row in existing_report.get("rows") or [] if isinstance(row, dict)]
    existing_by_key = {str(row.get("row_key") or ""): row for row in existing_rows if row.get("row_key")}
    enriched_rows = [row_with_document_evidence(row) for row in rows]
    enriched_by_key = {str(row.get("row_key") or ""): row for row in enriched_rows if row.get("row_key")}
    pending_rows = []
    retained_rows = []
    for row_key, row in enriched_by_key.items():
        signature = ai_triage_signature(row)
        existing = existing_by_key.get(row_key)
        if existing and existing.get("triage_signature") == signature:
            retained_rows.append(existing)
        else:
            pending_rows.append({**row, "triage_signature": signature})

    if not pending_rows:
        return {
            "ok": True,
            "skipped": True,
            "skip_reason": "NO_PENDING_AI_TRIAGE_ROWS",
            "summary": incremental_ai_triage_summary(retained_rows, []),
            "dashboard": dashboard_payload(scope=scope, sort=sort),
            "ai_triage_report": ai_triage_report_status(),
        }

    from tender_radar.ai_triage import build_ai_triage_report, write_ai_triage_report

    new_report = build_ai_triage_report(
        pending_rows,
        batch_size=max(1, min(int(batch_size), 50)),
        timeout_seconds=90,
    )
    pending_by_key = {str(row.get("row_key") or ""): row for row in pending_rows if row.get("row_key")}
    new_rows = []
    for row in new_report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("row_key") or "")
        prepared = pending_by_key.get(row_key, {})
        new_rows.append({**prepared, **row, "triage_signature": prepared.get("triage_signature") or row.get("triage_signature")})
    merged_rows = retained_rows + new_rows
    merged_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": new_report.get("model") or existing_report.get("model"),
        "input_rows": len(merged_rows),
        "summary": incremental_ai_triage_summary(merged_rows, new_report.get("errors") or []),
        "rows": merged_rows,
        "errors": new_report.get("errors") or [],
        "safety_note": new_report.get("safety_note") or existing_report.get("safety_note"),
        "incremental": True,
        "pending_rows": len(pending_rows),
        "retained_rows": len(retained_rows),
    }
    write_ai_triage_report(merged_report, ai_triage_report_path(), REPO_ROOT / "work/reports/ai_triage_report.md")
    return {
        "ok": int((merged_report.get("summary") or {}).get("errors") or 0) == 0,
        "skipped": False,
        "pending_rows": len(pending_rows),
        "retained_rows": len(retained_rows),
        "summary": merged_report["summary"],
        "dashboard": dashboard_payload(scope=scope, sort=sort),
        "ai_triage_report": ai_triage_report_status(),
    }


def row_with_document_evidence(row: dict[str, Any]) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("official_id") or row.get("display_id") or "").strip()
    if not row_key:
        return row
    documents = document_evidence_for_row(row, row_key=row_key)
    if not documents:
        return row
    existing_ids = [str(value) for value in row.get("linked_eshidis_ids") or [] if str(value).strip()]
    document_ids: list[str] = []
    for document in documents:
        document_ids.extend(str(value) for value in document.get("linked_eshidis_ids") or [] if str(value).strip())
    linked_ids = sorted({value for value in [*existing_ids, *document_ids] if value.isdigit()})
    deadline_evidence = best_deadline_evidence(documents)
    current_deadline = row.get("current_deadline_at") or row.get("submission_deadline")
    if not current_deadline and deadline_evidence:
        current_deadline = deadline_evidence.get("deadline_at")
    return {
        **row,
        "current_deadline_at": current_deadline,
        "deadline_evidence": deadline_evidence,
        "deadline_verification_status": "DOCUMENT_DEADLINE_EVIDENCE" if deadline_evidence else row.get("deadline_verification_status"),
        "document_evidence": documents,
        "document_evidence_count": len(documents),
        "linked_eshidis_ids": linked_ids,
    }


def ai_triage_signature(row: dict[str, Any]) -> str:
    stable = {
        "ai_triage_prompt_version": AI_TRIAGE_PROMPT_VERSION,
        "row_key": row.get("row_key"),
        "display_id": row.get("display_id"),
        "official_id": row.get("official_id"),
        "source_label": row.get("source_label"),
        "title": row.get("title"),
        "authority_name": row.get("authority_name"),
        "deadline": row.get("current_deadline_at") or row.get("submission_deadline"),
        "budget": row.get("budget_with_vat") or row.get("budget"),
        "official_url": row.get("official_url"),
        "attachment_urls": row.get("attachment_urls") or [],
        "linked_eshidis_ids": row.get("linked_eshidis_ids") or [],
        "document_evidence": row.get("document_evidence") or [],
    }
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def document_evidence_for_row(row: dict[str, Any], *, row_key: str) -> list[dict[str, Any]]:
    evidence_by_url: dict[str, dict[str, Any]] = {}
    for document in sqlite_source_document_evidence(row_key):
        evidence_by_url[str(document.get("document_url") or document.get("name") or len(evidence_by_url))] = document
    for document in legacy_row_document_evidence(row, row_key=row_key):
        evidence_by_url.setdefault(str(document.get("document_url") or document.get("name") or len(evidence_by_url)), document)
    evidence = list(evidence_by_url.values())
    evidence.sort(key=lambda item: document_evidence_rank(item))
    return evidence[:4]


def sqlite_source_document_evidence(row_key: str) -> list[dict[str, Any]]:
    try:
        source_documents = list_source_documents(runtime_db_path(), row_key=row_key)
    except (OSError, sqlite3.Error):
        return []
    evidence: list[dict[str, Any]] = []
    for source_document in source_documents:
        metadata = source_document.metadata if isinstance(source_document.metadata, dict) else {}
        evidence.append(
            document_evidence_payload(
                row_key=row_key,
                document_url=source_document.document_url,
                source_url=source_document.source_url,
                local_path=source_document.local_path,
                metadata=metadata,
                fetch_error=source_document.fetch_error,
            )
        )
    return evidence


def legacy_row_document_evidence(row: dict[str, Any], *, row_key: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if row_key.startswith("KIMDIS:"):
        official_id = row_key.split(":", 1)[1]
        document = kimdis_documents_by_official_id().get(official_id)
        if isinstance(document, dict):
            documents.append(document)
    else:
        documents.extend(document for document in authority_documents_by_key().get(row_key, []) if isinstance(document, dict))
    evidence: list[dict[str, Any]] = []
    for document in documents:
        metadata = {
            "document_analysis": document.get("document_analysis"),
            "text_path": document.get("text_path"),
            "linked_eshidis_ids": document.get("linked_eshidis_ids"),
        }
        evidence.append(
            document_evidence_payload(
                row_key=row_key,
                document_url=str(document.get("attachment_url") or document.get("document_url") or ""),
                source_url=str(document.get("source_url") or row.get("official_url") or ""),
                local_path=_none_or_str(document.get("local_path")),
                metadata=metadata,
                fetch_error=_none_or_str(document.get("fetch_error")),
            )
        )
    return evidence


def document_evidence_payload(
    *,
    row_key: str,
    document_url: str | None,
    source_url: str | None,
    local_path: str | None,
    metadata: dict[str, Any],
    fetch_error: str | None,
) -> dict[str, Any]:
    analysis = metadata.get("document_analysis") if isinstance(metadata.get("document_analysis"), dict) else {}
    text_path = _none_or_str(metadata.get("text_path")) or _none_or_str(analysis.get("text_path"))
    local = normalize_local_path(local_path)
    name = Path(local_path).name if local_path else Path(str(urlparse(str(document_url or "")).path)).name
    text = read_document_text_sample(text_path=text_path, fallback=_none_or_str(analysis.get("full_text") or analysis.get("text_sample")))
    linked_ids = sorted(
        {
            *[str(value) for value in metadata.get("linked_eshidis_ids") or [] if str(value).strip()],
            *extract_eshidis_ids_from_text(name, document_url, source_url, text),
        }
    )
    deadline_evidence = extract_deadline_evidence_from_text(
        text,
        document_name=name or "document",
        document_url=document_url,
        source_url=source_url,
    )
    return {
        "row_key": row_key,
        "name": name or "document",
        "document_url": document_url,
        "source_url": source_url,
        "local_path_available": bool(local and local.exists()),
        "document_type": analysis.get("document_type"),
        "extraction_status": analysis.get("extraction_status"),
        "ocr_status": analysis.get("ocr_status") or "UNKNOWN",
        "ocr_error": analysis.get("ocr_error"),
        "fetch_error": fetch_error,
        "linked_eshidis_ids": [value for value in linked_ids if value.isdigit()],
        "deadline_evidence": deadline_evidence,
        "snippets": select_document_snippets(text),
    }


def read_document_text_sample(*, text_path: str | None, fallback: str | None, limit: int = 16000) -> str:
    path = normalize_local_path(text_path)
    if path and path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        except OSError:
            pass
    return (fallback or "")[:limit]


def select_document_snippets(text: str, *, max_snippets: int = 5, radius: int = 420) -> list[str]:
    if not text.strip():
        return []
    normalized = text.replace("\r", "\n")
    snippets: list[str] = []
    snippets.append(compact_document_snippet(normalized[:900]))
    markers = [
        "2.2",
        "προθεσμία",
        "προθεσμια",
        "καταληκτική",
        "καταληκτικη",
        "υποβολή προσφορών",
        "υποβολη προσφορων",
        "ημερομηνία λήξης",
        "ημερομηνια ληξης",
        "παράταση",
        "παραταση",
        "ΕΣΗΔΗΣ",
        "Ε.Σ.Η.Δ",
        "Α/Α",
        "Α/Α Διαγωνισμού",
        "Α/Α Συστήματος",
        "pwgopendata",
        "publicworks.eprocurement",
        "actSearchErgwn",
        "ΟΙΚΟΝΟΜΙΚΗΣ ΠΡΟΣΦΟΡΑΣ",
    ]
    lowered = normalized.casefold()
    for marker in markers:
        index = lowered.find(marker.casefold())
        if index < 0:
            continue
        start = max(0, index - radius)
        end = min(len(normalized), index + radius)
        snippet = compact_document_snippet(normalized[start:end])
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= max_snippets:
            break
    return snippets[:max_snippets]


def compact_document_snippet(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:1200]


def compact_full_document_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def document_evidence_rank(item: dict[str, Any]) -> tuple[int, str]:
    name = normalize_greek(str(item.get("name") or ""))
    doc_type = normalize_greek(str(item.get("document_type") or ""))
    if "διακηρυ" in name or "declaration" in doc_type:
        rank = 0
    elif "οικονομικ" in name or "προσφορ" in name:
        rank = 1
    elif item.get("linked_eshidis_ids"):
        rank = 2
    else:
        rank = 3
    return rank, name


def best_deadline_evidence(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for document in documents:
        evidence = document.get("deadline_evidence") if isinstance(document.get("deadline_evidence"), dict) else None
        if not evidence:
            continue
        deadline_at = str(evidence.get("deadline_at") or "")
        if deadline_sort_key(deadline_at) == "9999":
            continue
        candidates.append(evidence)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            deadline_sort_key(str(item.get("deadline_at") or "")),
            1 if item.get("is_extension") else 0,
            float(item.get("confidence") or 0),
        ),
        reverse=True,
    )[0]


def extract_deadline_evidence_from_text(
    text: str,
    *,
    document_name: str,
    document_url: str | None,
    source_url: str | None,
) -> dict[str, Any] | None:
    if not text.strip():
        return None
    normalized = compact_full_document_text(text)
    matches: list[dict[str, Any]] = []
    for match in _date_candidate_matches(normalized):
        start, end = match["span"]
        context = normalized[max(0, start - 260) : min(len(normalized), end + 260)]
        score = deadline_context_score(context)
        if score <= 0:
            continue
        matches.append(
            {
                "deadline_at": match["deadline_at"],
                "document_name": document_name,
                "document_url": document_url,
                "source_url": source_url,
                "snippet": context[:900],
                "matched_text": match["matched_text"],
                "is_extension": deadline_context_is_extension(context),
                "confidence": min(0.98, 0.55 + score * 0.1),
                "evidence_status": "DEADLINE_EVIDENCE_FOUND",
            }
        )
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda item: (
            deadline_sort_key(str(item.get("deadline_at") or "")),
            1 if item.get("is_extension") else 0,
            float(item.get("confidence") or 0),
        ),
        reverse=True,
    )[0]


def _date_candidate_matches(text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    patterns = [
        re.compile(
            r"(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>20\d{2})"
            r"(?:\s*(?:και\s*)?(?:ώρα|ωρα)?\s*(?P<hour>\d{1,2})[:.](?P<minute>\d{2})(?::\d{2})?)?",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
            r"(?:[T\s]+(?P<hour>\d{1,2})[:.](?P<minute>\d{2})(?::\d{2}(?:\.\d+)?)?)?",
            flags=re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            try:
                year = int(match.group("year"))
                month = int(match.group("month"))
                day = int(match.group("day"))
                hour = int(match.group("hour") or 0)
                minute = int(match.group("minute") or 0)
                parsed = date(year, month, day)
            except (TypeError, ValueError):
                continue
            deadline_at = f"{parsed.isoformat()} {hour:02d}:{minute:02d}" if match.group("hour") else parsed.isoformat()
            matches.append(
                {
                    "deadline_at": deadline_at,
                    "matched_text": match.group(0),
                    "span": match.span(),
                }
            )
    return matches


def deadline_context_score(context: str) -> int:
    normalized = normalize_greek(context)
    positive_groups = [
        ("προθεσμια", "καταληκτικ", "ληξη"),
        ("υποβολ", "προσφορ"),
        ("διαγωνισμ", "συμβαση"),
        ("παραταση", "παρατειν"),
    ]
    score = 0
    for group in positive_groups:
        if any(term in normalized for term in group):
            score += 1
    negative_terms = (
        "ημερομηνια δημοσιευση",
        "ημερομηνια συνεδριαση",
        "αποσφραγιση",
        "υπογραφη",
        "πρωτοκολλ",
        "φεκ",
    )
    if any(term in normalized for term in negative_terms):
        score -= 1
    return score


def deadline_context_is_extension(context: str) -> bool:
    normalized = normalize_greek(context)
    return any(term in normalized for term in ("παραταση", "παρατειν", "νεα καταληκτικ"))


def load_ai_triage_report_payload() -> dict[str, Any]:
    path = ai_triage_report_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def incremental_ai_triage_summary(rows: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    kept = 0
    dropped = 0
    for row in rows:
        ai = row.get("ai") if isinstance(row.get("ai"), dict) else {}
        decision = str(ai.get("decision") or "REVIEW_TENDER_CANDIDATE")
        decisions[decision] = decisions.get(decision, 0) + 1
        if ai.get("keep_for_daily_review"):
            kept += 1
        else:
            dropped += 1
    return {"decisions": decisions, "kept_total": kept, "dropped_total": dropped, "errors": len(errors)}


def run_candidate_enrichment(*, scope: str = "focus", limit: int = 50, max_seconds: float | None = None) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("Enrichment limit must be positive.")
    if not ENRICHMENT_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another candidate enrichment is already running."}
    attempt_records: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    started_monotonic = time.monotonic()
    stopped_by_time_budget = False
    try:
        targets, skipped = candidate_enrichment_targets(scope=scope, limit=limit)
        for target in targets:
            if max_seconds is not None and time.monotonic() - started_monotonic >= max_seconds:
                stopped_by_time_budget = True
                break
            identifier = str(target["identifier"])
            result = run_selected_fetch(identifier)
            linked_ids = [str(value) for value in result.get("linked_eshidis_ids") or [] if str(value).strip()]
            verified_link_ids = persist_verified_eshidis_links_for_enrichment(target, result)
            record = {
                "row_key": target["row_key"],
                "identifier": identifier,
                "kind": target["kind"],
                "source_signature": target["source_signature"],
                "attempted_at": utc_now_iso(),
                "ok": result.get("ok") is not False,
                "linked_eshidis_ids": linked_ids,
                "verified_eshidis_ids": verified_link_ids,
                "official_fetch_ok": (result.get("eshidis_fetch") or {}).get("ok"),
            }
            attempt_records.append(record)
            results.append(
                {
                    **record,
                    "error": result.get("error"),
                    "downloaded": result.get("downloaded"),
                    "failed": result.get("failed"),
                }
            )
        if attempt_records:
            write_candidate_enrichment_attempts(attempt_records)
        enriched = [item for item in results if item.get("linked_eshidis_ids")]
        verified = [item for item in results if item.get("verified_eshidis_ids")]
        failed = [item for item in results if item.get("ok") is False]
        return {
            "ok": not failed,
            "summary": {
                "targets": len(targets),
                "attempted": len(results),
                "enriched_with_eshidis": len(enriched),
                "verified_eshidis_links": sum(len(item.get("verified_eshidis_ids") or []) for item in verified),
                "failed": len(failed),
                "skipped_previously_attempted": skipped,
                "stopped_by_time_budget": stopped_by_time_budget,
                "remaining_targets": max(0, len(targets) - len(results)),
            },
            "results": results,
            "dashboard": dashboard_payload(scope=scope if scope in {"focus", "all"} else "focus"),
        }
    finally:
        ENRICHMENT_LOCK.release()


def persist_verified_eshidis_links_for_enrichment(target: dict[str, str], result: dict[str, Any]) -> list[str]:
    if result.get("ok") is False:
        return []
    identifier = str(target.get("identifier") or "").strip()
    linked_ids = [str(value) for value in result.get("linked_eshidis_ids") or [] if str(value).strip().isdigit()]
    if identifier.isdigit():
        linked_ids.append(identifier)
    linked_ids = sorted(set(linked_ids))
    if not linked_ids:
        return []
    eshidis_fetch = result.get("eshidis_fetch")
    official_fetch_ok = bool(eshidis_fetch.get("ok")) if isinstance(eshidis_fetch, dict) else identifier.isdigit()
    if not official_fetch_ok:
        return []
    row_key = str(target.get("row_key") or "").strip()
    if not row_key:
        return []
    delete_stale_verified_tender_links(
        runtime_db_path(),
        source_row_key=row_key,
        keep_target_eshidis_ids=set(linked_ids),
    )
    verified_at = utc_now_iso()
    verified_ids: list[str] = []
    for eshidis_id in linked_ids:
        upsert_verified_tender_link(
            runtime_db_path(),
            source_row_key=row_key,
            source_identifier=identifier,
            source_label=str(target.get("kind") or ""),
            source_url=str(target.get("source_url") or "") or None,
            target_eshidis_id=eshidis_id,
            verification_status="VERIFIED_ESHIDIS_RESOURCE",
            verified_at=verified_at,
            source_signature=str(target.get("source_signature") or "") or None,
            evidence={
                "verification": "official_eshidis_fetch",
                "identifier_used": identifier,
                "linked_eshidis_ids": linked_ids,
                "official_fetch_ok": official_fetch_ok,
                "steps": [
                    {"name": step.get("name"), "returncode": step.get("returncode")}
                    for step in (
                        eshidis_fetch.get("steps") if isinstance(eshidis_fetch, dict) else result.get("steps")
                    )
                    or []
                    if isinstance(step, dict)
                ],
            },
        )
        verified_ids.append(eshidis_id)
    return verified_ids


def persist_verified_links_for_selected_fetch(
    *,
    source_row_key: str,
    source_identifier: str,
    source_label: str,
    linked_ids: list[str],
    eshidis_fetch: dict[str, Any],
) -> list[str]:
    if not linked_ids or eshidis_fetch.get("ok") is False:
        return []
    current_ids = {str(value).strip() for value in linked_ids if str(value).strip().isdigit()}
    delete_stale_verified_tender_links(
        runtime_db_path(),
        source_row_key=source_row_key,
        keep_target_eshidis_ids=current_ids,
    )
    verified_at = utc_now_iso()
    verified_ids: list[str] = []
    for eshidis_id in sorted({str(value).strip() for value in linked_ids if str(value).strip().isdigit()}):
        upsert_verified_tender_link(
            runtime_db_path(),
            source_row_key=source_row_key,
            source_identifier=source_identifier,
            source_label=source_label,
            source_url=None,
            target_eshidis_id=eshidis_id,
            verification_status="VERIFIED_ESHIDIS_RESOURCE",
            verified_at=verified_at,
            source_signature=None,
            evidence={
                "verification": "manual_selected_fetch",
                "source_identifier": source_identifier,
                "linked_eshidis_ids": linked_ids,
                "official_fetch_ok": eshidis_fetch.get("ok") is not False,
                "steps": [
                    {"name": step.get("name"), "returncode": step.get("returncode")}
                    for step in eshidis_fetch.get("steps", [])
                    if isinstance(step, dict)
                ],
            },
        )
        verified_ids.append(eshidis_id)
    return verified_ids


def run_auto_document_fetch(
    *,
    scope: str = "focus",
    limit: int = 50,
    max_seconds: float | None = DEFAULT_SCHEDULED_AUTO_FETCH_SECONDS,
) -> dict[str, Any]:
    result = run_candidate_enrichment(scope=scope, limit=limit, max_seconds=max_seconds)
    result["stage"] = "auto_document_fetch"
    result["max_seconds"] = max_seconds
    result["purpose"] = (
        "Fetch documents for new, changed or unprocessed non-ESHIDIS rows before "
        "email/UI presentation. Existing attempts and source_documents prevent "
        "unnecessary re-downloads."
    )
    return result


def candidate_enrichment_targets(*, scope: str = "focus", limit: int = 50) -> tuple[list[dict[str, str]], int]:
    dashboard = dashboard_payload(scope=scope if scope in {"focus", "all"} else "focus")
    attempts = candidate_enrichment_attempts()
    canonical_ids = canonical_eshidis_ids_in_rows(merged_tender_rows())
    targets: list[dict[str, str]] = []
    skipped = 0
    for row in dashboard.get("tenders") or []:
        if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ":
            continue
        row_key = str(row.get("row_key") or row.get("official_id") or row.get("display_id") or "").strip()
        if not row_key:
            continue
        linked_ids = set(linked_eshidis_ids_for_row(row))
        if linked_ids and linked_ids <= canonical_ids:
            continue
        signature = candidate_enrichment_signature(row)
        previous = attempts.get(row_key)
        if previous and previous.get("source_signature") == signature:
            skipped += 1
            continue
        identifier = candidate_enrichment_identifier(row)
        if not identifier:
            continue
        targets.append(
            {
                "row_key": row_key,
                "identifier": identifier,
                "kind": str(row.get("source_label") or ""),
                "source_url": str(row.get("official_url") or row.get("source_url") or ""),
                "source_signature": signature,
            }
        )
        if len(targets) >= limit:
            break
    return targets, skipped


def candidate_enrichment_identifier(row: dict[str, Any]) -> str | None:
    row_key = str(row.get("row_key") or "").strip()
    official_id = str(row.get("official_id") or row.get("display_id") or "").strip()
    linked_ids = linked_eshidis_ids_for_row(row)
    if linked_ids:
        return linked_ids[0]
    if row.get("supports_authority_actions") and row_key:
        return row_key
    if row.get("supports_kimdis_actions") and is_kimdis_identifier(official_id):
        return official_id
    if str(row.get("eshidis_id") or "").isdigit():
        return str(row.get("eshidis_id"))
    return None


def candidate_enrichment_signature(row: dict[str, Any]) -> str:
    parts = [
        row.get("row_key"),
        row.get("official_id"),
        row.get("display_id"),
        row.get("title"),
        row.get("authority_name"),
        row.get("published_at"),
        row.get("current_deadline_at"),
        row.get("official_url"),
        row.get("attachment_url"),
        " ".join(str(value) for value in row.get("attachment_urls") or []),
    ]
    raw = "\n".join(str(value or "") for value in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def candidate_enrichment_attempts_path() -> Path:
    return REPO_ROOT / "work/derived/candidate_enrichment_attempts.json"


def candidate_enrichment_attempts() -> dict[str, dict[str, Any]]:
    path = candidate_enrichment_attempts_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    attempts: dict[str, dict[str, Any]] = {}
    for item in payload.get("attempts") or []:
        if not isinstance(item, dict):
            continue
        row_key = str(item.get("row_key") or "").strip()
        if row_key:
            attempts[row_key] = item
    return attempts


def write_candidate_enrichment_attempts(attempt_records: list[dict[str, Any]]) -> None:
    path = candidate_enrichment_attempts_path()
    existing = candidate_enrichment_attempts()
    for item in attempt_records:
        row_key = str(item.get("row_key") or "").strip()
        if row_key:
            existing[row_key] = item
    payload = {"updated_at": utc_now_iso(), "attempts": list(existing.values())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
                if preflight.get("current"):
                    save_source_fingerprint(preflight["current"])
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
            enrichment_results, linked_enrichment = run_linked_eshidis_enrichment()
            for result in enrichment_results:
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
                if pass_ok and preflight and preflight.get("current"):
                    save_source_fingerprint(quick_source_fingerprint(timeout_seconds=8))
                response = discovery_response(results, warnings, pass_ok, records, preflight)
                response["linked_eshidis_enrichment"] = linked_enrichment
                return response
            if record.get("watermark", {}).get("complete"):
                if pass_ok and preflight and preflight.get("current", {}).get("ok"):
                    save_source_fingerprint(preflight["current"])
                response = discovery_response(results, warnings, pass_ok, records, preflight)
                response["linked_eshidis_enrichment"] = linked_enrichment
                return response
            if current_limit >= MAX_BACKFILL_ESHIDIS_LIMIT and current_kimdis_pages >= MAX_BACKFILL_KIMDIS_PAGES:
                response = discovery_response(results, warnings, False, records, preflight)
                response["linked_eshidis_enrichment"] = linked_enrichment
                return response
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
    persist_source_preflight_state(current=current, previous=previous)
    reports_exist = (REPO_ROOT / "work/reports/expanded_discovery_report.json").exists()
    changed_source_ids = _changed_source_ids(current=current, previous=previous)
    exact_skip = bool(
        reports_exist
        and current.get("ok")
        and previous
        and (
            (previous.get("hash") and previous.get("hash") == current.get("hash"))
            or (previous.get("state_source") == "sqlite" and previous.get("sources") and not changed_source_ids)
        )
    )
    partial_skip = bool(
        reports_exist
        and current.get("errors")
        and previous
        and _successful_sources_unchanged(current=current, previous=previous)
    )
    degraded_skip = bool(
        reports_exist
        and current.get("errors")
        and previous
        and not changed_source_ids
    )
    skip = exact_skip or partial_skip or degraded_skip
    status = "CHANGED_OR_NO_BASELINE"
    if exact_skip:
        status = "SKIPPED_UNCHANGED"
    elif partial_skip:
        status = "SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS"
    elif degraded_skip:
        status = "SKIPPED_DEGRADED_NO_SUCCESSFUL_SOURCE_CHANGES"
    return {
        "ok": current.get("ok"),
        "skip": skip,
        "status": status,
        "changed_source_ids": changed_source_ids,
        "current": current,
        "previous_hash": previous.get("hash") if previous else None,
        "current_hash": current.get("hash"),
        "errors": current.get("errors") or [],
    }


def latest_source_fingerprint() -> dict[str, Any] | None:
    sqlite_latest = latest_source_fingerprint_from_db()
    if sqlite_latest:
        return sqlite_latest
    path = source_fingerprint_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("latest"), dict):
        return payload["latest"]
    return payload.get("latest_complete") if isinstance(payload.get("latest_complete"), dict) else None


def save_source_fingerprint(fingerprint: dict[str, Any]) -> None:
    persist_source_preflight_state(current=fingerprint, previous=latest_source_fingerprint_from_json())
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


def latest_source_fingerprint_from_json() -> dict[str, Any] | None:
    path = source_fingerprint_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("latest"), dict):
        return payload["latest"]
    return payload.get("latest_complete") if isinstance(payload.get("latest_complete"), dict) else None


def latest_source_fingerprint_from_db() -> dict[str, Any] | None:
    db_path = runtime_db_path()
    source_ids = selective_source_ids_from_config()
    if not source_ids:
        return None
    sources: list[dict[str, Any]] = []
    checked_at_values: list[str] = []
    for source_id in sorted(source_ids):
        state = get_source_state(db_path, source_id)
        if state is None:
            return None
        if state.last_checked_at:
            checked_at_values.append(state.last_checked_at)
        source = {
            "source_id": state.source_id,
            "source_group": state.metadata.get("source_group"),
            "adapter": state.metadata.get("adapter"),
            "url": state.source_url,
            "status": state.last_status,
            "attempted": state.metadata.get("attempted"),
            "reachable": state.metadata.get("reachable"),
            "token": state.metadata.get("token"),
            "date": state.metadata.get("date"),
            "count_hint": state.metadata.get("count_hint"),
        }
        sources.append({key: value for key, value in source.items() if value is not None})
    digest = hashlib.sha256(json.dumps(sources, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "ok": all(source.get("reachable") is True or source.get("status") == "REQUIRES_IDENTIFIER" for source in sources),
        "computed_at": max(checked_at_values, default=None),
        "hash": digest,
        "sources": sources,
        "errors": [],
        "state_source": "sqlite",
    }


def persist_source_preflight_state(*, current: dict[str, Any], previous: dict[str, Any] | None = None) -> None:
    db_path = runtime_db_path()
    run_id = str(current.get("run_id") or uuid.uuid4().hex)
    checked_at = str(current.get("computed_at") or utc_now_iso())
    previous_by_id = {
        str(item.get("source_id") or ""): _source_fingerprint_signature(item)
        for item in (previous or {}).get("sources") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    current_by_id = {
        str(item.get("source_id") or ""): item
        for item in current.get("sources") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    error_by_id = {
        str(item.get("source") or ""): str(item.get("message") or "")
        for item in current.get("errors") or []
        if isinstance(item, dict) and item.get("source")
    }
    for source_id, source in sorted(current_by_id.items()):
        signature = _source_fingerprint_signature(source)
        fingerprint = hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        changed = previous_by_id.get(source_id) != signature
        status = "CHANGED" if changed else "SKIPPED_UNCHANGED"
        if source.get("status") == "REQUIRES_IDENTIFIER":
            status = "REQUIRES_IDENTIFIER"
        elif source.get("reachable") is not True:
            status = "ERROR"
        metadata = {
            "adapter": source.get("adapter"),
            "source_group": source.get("source_group"),
            "attempted": source.get("attempted"),
            "reachable": source.get("reachable"),
            "token": source.get("token"),
            "date": source.get("date"),
            "count_hint": source.get("count_hint"),
        }
        upsert_source_state(
            db_path,
            source_id=source_id,
            source_family=str(source.get("adapter") or "") or None,
            source_url=str(source.get("url") or "") or None,
            fingerprint=fingerprint,
            checked_at=checked_at,
            status=status,
            error=error_by_id.get(source_id),
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
        record_source_run(
            db_path,
            run_id=run_id,
            source_id=source_id,
            started_at=checked_at,
            finished_at=checked_at,
            status=status,
            fingerprint=fingerprint,
            changed=changed,
            item_count=int(source["count_hint"]) if isinstance(source.get("count_hint"), int) else None,
            error=error_by_id.get(source_id),
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
    for source_id, message in sorted(error_by_id.items()):
        if source_id in current_by_id:
            continue
        previous_state = get_source_state(db_path, source_id)
        metadata = dict(previous_state.metadata) if previous_state else {}
        metadata["reachable"] = False
        upsert_source_state(
            db_path,
            source_id=source_id,
            source_family=previous_state.source_family if previous_state else None,
            source_url=previous_state.source_url if previous_state else None,
            fingerprint=previous_state.fingerprint if previous_state else None,
            checked_at=checked_at,
            status="ERROR",
            error=message,
            metadata=metadata,
        )
        record_source_run(
            db_path,
            run_id=run_id,
            source_id=source_id,
            started_at=checked_at,
            finished_at=checked_at,
            status="ERROR",
            fingerprint=previous_state.fingerprint if previous_state else None,
            changed=False,
            error=message,
            metadata=metadata,
        )


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
    discovery_relevant_ids = selective_source_ids_from_config()
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
        if source_id not in discovery_relevant_ids:
            continue
        if previous_sources.get(source_id) != _source_fingerprint_signature(item):
            changed.append(source_id)
    return sorted(changed)


def source_polling_payload() -> dict[str, Any]:
    config_path = REPO_ROOT / "config/sources.yml"
    config = load_config(config_path) if config_path.exists() else {}
    configured_entries = configured_source_entries(config)
    configured_by_id = {str(entry.get("id") or ""): entry for entry in configured_entries if entry.get("id")}
    source_states = {state.source_id: state for state in list_source_states(runtime_db_path())}
    selective_ids = selective_source_ids_from_config()
    ordered_ids = [str(entry.get("id") or "") for entry in configured_entries if entry.get("id")]
    ordered_ids.extend(sorted(source_id for source_id in source_states if source_id not in set(ordered_ids)))

    rows: list[dict[str, Any]] = []
    for source_id in ordered_ids:
        entry = configured_by_id.get(source_id, {})
        state = source_states.get(source_id)
        metadata = dict(state.metadata) if state else {}
        state_family = state.source_family if state and state.source_family else None
        adapter = str(
            metadata.get("adapter")
            or entry.get("adapter")
            or entry.get("type")
            or state_family
            or ""
        )
        last_status = state.last_status if state else "NEVER_CHECKED"
        rows.append(
            {
                "source_id": source_id,
                "name": entry.get("name") or source_id,
                "source_group": metadata.get("source_group") or entry.get("source_group"),
                "family_or_adapter": adapter or None,
                "source_url": state.source_url if state and state.source_url else entry.get("url"),
                "last_status": last_status,
                "last_checked_at": state.last_checked_at if state else None,
                "last_changed_at": state.last_changed_at if state else None,
                "last_error": state.last_error if state else None,
                "changed": last_status == "CHANGED",
                "selective_refresh_capable": source_id in selective_ids,
                "attempted": metadata.get("attempted"),
                "reachable": metadata.get("reachable"),
                "count_hint": metadata.get("count_hint"),
            }
        )

    latest_checked_values = [str(row["last_checked_at"]) for row in rows if row.get("last_checked_at")]
    summary = {
        "configured_total": len(configured_entries),
        "tracked_total": len(source_states),
        "changed_total": sum(1 for row in rows if row["last_status"] == "CHANGED"),
        "selective_changed_total": sum(
            1 for row in rows if row["last_status"] == "CHANGED" and row["selective_refresh_capable"]
        ),
        "unchanged_total": sum(1 for row in rows if row["last_status"] == "SKIPPED_UNCHANGED"),
        "error_total": sum(1 for row in rows if row["last_status"] == "ERROR" or row.get("last_error")),
        "selective_error_total": sum(
            1
            for row in rows
            if row["selective_refresh_capable"] and (row["last_status"] == "ERROR" or row.get("last_error"))
        ),
        "requires_identifier_total": sum(1 for row in rows if row["last_status"] == "REQUIRES_IDENTIFIER"),
        "never_checked_total": sum(1 for row in rows if row["last_status"] == "NEVER_CHECKED"),
        "selective_capable_total": sum(1 for row in rows if row["selective_refresh_capable"]),
        "last_checked_at": max(latest_checked_values, default=None),
    }
    return {
        "ok": True,
        "summary": summary,
        "rows": rows,
    }


def run_email_alerts(
    *,
    scope: str = "focus",
    sort: str = "deadline_asc",
    recipient: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = email_alerts_payload(scope=scope, sort=sort, recipient=recipient, dry_run=dry_run)
    if dry_run or not payload["new_rows"]:
        return payload
    send_email_alert(payload["recipient"], payload["subject"], payload["text_body"], payload["html_body"])
    sent_at = utc_now_iso()
    for row in payload["new_rows"]:
        record_notification_sent(
            runtime_db_path(),
            row_key=str(row["row_key"]),
            channel="email",
            recipient=payload["recipient"],
            subject=payload["subject"],
            sent_at=sent_at,
            metadata={
                "display_id": row.get("display_id"),
                "source_label": row.get("source_label"),
                "official_url": row.get("official_url"),
            },
        )
    payload["sent"] = len(payload["new_rows"])
    payload["sent_at"] = sent_at
    return payload


def run_scheduled_poll_and_alert(
    *,
    scope: str = "focus",
    sort: str = "deadline_asc",
    limit: int = DEFAULT_ESHIDIS_DISCOVERY_LIMIT,
    ai_batch_size: int = 20,
    enrichment_limit: int = 50,
    recipient: str | None = None,
    dry_run: bool = False,
    report_path: Path | None = None,
    markdown_report_path: Path | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    discovery = run_discovery_search(limit=limit, backfill=False)
    if discovery.get("ok") is False:
        errors.append({"stage": "discovery", "message": str(discovery.get("error") or "discovery failed")})

    ai_result: dict[str, Any] = {"ok": True, "skipped": False}
    auto_document_fetch: dict[str, Any] = {"ok": True, "skipped": False}
    email_result: dict[str, Any] = {"ok": True, "skipped": False}
    if discovery.get("ok") is not False:
        discovery_skipped = bool(discovery.get("skipped"))
        ai_result = run_incremental_ai_triage(scope=scope, sort=sort, batch_size=ai_batch_size)
        if ai_result.get("ok") is False:
            errors.append({"stage": "ai_triage", "message": str(ai_result.get("error") or "AI triage failed")})
        if discovery_skipped:
            auto_document_fetch = {
                "ok": True,
                "skipped": True,
                "skip_reason": "DISCOVERY_SKIPPED_NO_NEW_ROWS",
                "discovery_skipped": True,
            }
        else:
            auto_document_fetch = run_auto_document_fetch(scope=scope, limit=enrichment_limit)
            if auto_document_fetch.get("ok") is False:
                warnings.append(
                    {
                        "stage": "auto_document_fetch",
                        "message": str(auto_document_fetch.get("error") or "automatic document fetch failed"),
                    }
                )
        try:
            email_result = run_email_alerts(scope=scope, sort=sort, recipient=recipient, dry_run=dry_run)
        except Exception as exc:
            email_result = {"ok": False, "error": str(exc), "dry_run": dry_run}
            errors.append({"stage": "email_alerts", "message": str(exc)})

    source_polling = source_polling_payload()
    completed_at = utc_now_iso()
    changed_source_ids = (discovery.get("source_preflight") or {}).get("changed_source_ids") or []
    changed_source_id_set = {str(source_id) for source_id in changed_source_ids}
    payload: dict[str, Any] = {
        "ok": not errors,
        "dry_run": dry_run,
        "started_at": started_at,
        "completed_at": completed_at,
        "scope": scope,
        "sort": sort,
        "limit": limit,
        "source_polling_summary": source_polling.get("summary") or {},
        "changed_source_ids": changed_source_ids,
        "skipped_sources": [
            row["source_id"]
            for row in source_polling.get("rows") or []
            if row.get("last_status") == "SKIPPED_UNCHANGED" and str(row.get("source_id") or "") not in changed_source_id_set
        ],
        "source_errors": [
            {"source_id": row.get("source_id"), "error": row.get("last_error")}
            for row in source_polling.get("rows") or []
            if row.get("last_error")
        ],
        "discovery": summarize_scheduled_stage(discovery),
        "ai_triage": summarize_scheduled_stage(ai_result),
        "auto_document_fetch": summarize_scheduled_stage(auto_document_fetch),
        "enrichment": summarize_scheduled_stage(auto_document_fetch),
        "email": summarize_email_result(email_result),
        "errors": errors,
        "warnings": warnings,
    }
    write_scheduled_run_reports(payload, report_path=report_path, markdown_report_path=markdown_report_path)
    return payload


def summarize_scheduled_stage(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result.get("ok"),
        "skipped": result.get("skipped"),
        "error": result.get("error"),
        "steps": [
            {"name": step.get("name"), "returncode": step.get("returncode")}
            for step in result.get("steps") or []
            if isinstance(step, dict)
        ],
        "summary": result.get("summary") or (result.get("dashboard") or {}).get("summary") or {},
    }


def summarize_email_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result.get("ok"),
        "dry_run": result.get("dry_run"),
        "recipient": result.get("recipient"),
        "candidate_rows": result.get("candidate_rows"),
        "new_count": result.get("new_count"),
        "skipped_already_sent": result.get("skipped_already_sent"),
        "sent": result.get("sent"),
        "error": result.get("error"),
    }


def scheduled_report_default_path() -> Path:
    return REPO_ROOT / "work/reports/scheduled_poll_alert_latest.json"


def scheduled_markdown_default_path() -> Path:
    return REPO_ROOT / "work/reports/scheduled_poll_alert_latest.md"


def write_scheduled_run_reports(
    payload: dict[str, Any],
    *,
    report_path: Path | None = None,
    markdown_report_path: Path | None = None,
) -> None:
    json_path = report_path or scheduled_report_default_path()
    markdown_path = markdown_report_path or scheduled_markdown_default_path()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_scheduled_run_markdown(payload), encoding="utf-8")


def render_scheduled_run_markdown(payload: dict[str, Any]) -> str:
    source_summary = payload.get("source_polling_summary") or {}
    email = payload.get("email") or {}
    lines = [
        "# Scheduled Poll and Alert",
        "",
        f"- Started: {payload.get('started_at')}",
        f"- Completed: {payload.get('completed_at')}",
        f"- Dry run: {payload.get('dry_run')}",
        f"- OK: {payload.get('ok')}",
        "",
        "## Sources",
        "",
        f"- Configured: {source_summary.get('configured_total')}",
        f"- Selective capable: {source_summary.get('selective_capable_total')}",
        f"- Changed: {source_summary.get('changed_total')}",
        f"- Selective changed: {source_summary.get('selective_changed_total')}",
        f"- Skipped unchanged: {source_summary.get('unchanged_total')}",
        f"- Errors: {source_summary.get('error_total')}",
        "",
        "## Email",
        "",
        f"- Candidate rows: {email.get('candidate_rows')}",
        f"- New rows: {email.get('new_count')}",
        f"- Already sent: {email.get('skipped_already_sent')}",
        f"- Sent: {email.get('sent')}",
        "",
        "## Changed Sources",
        "",
    ]
    changed = payload.get("changed_source_ids") or []
    lines.extend(f"- {source_id}" for source_id in changed)
    if not changed:
        lines.append("- none")
    lines.extend(["", "## Errors", ""])
    errors = payload.get("errors") or []
    lines.extend(f"- {item.get('stage')}: {item.get('message')}" for item in errors)
    if not errors:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = payload.get("warnings") or []
    lines.extend(f"- {item.get('stage')}: {item.get('message')}" for item in warnings)
    if not warnings:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def email_alerts_payload(
    *,
    scope: str = "focus",
    sort: str = "deadline_asc",
    recipient: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    target = recipient or email_alert_recipient()
    if not target:
        raise ValueError("Email recipient is not configured. Set ALERT_EMAIL_TO or pass recipient.")
    dashboard = dashboard_payload(scope=scope, sort=sort)
    rows = [email_alert_row(row) for row in dashboard.get("tenders") or []]
    rows = [row for row in rows if row["row_key"]]
    skipped = [
        row
        for row in rows
        if notification_already_sent(runtime_db_path(), row_key=row["row_key"], channel="email", recipient=target)
    ]
    skipped_keys = {row["row_key"] for row in skipped}
    new_rows = [row for row in rows if row["row_key"] not in skipped_keys]
    subject = f"Tender Radar: {len(new_rows)} νέα έργα"
    text_body = render_email_text(new_rows)
    html_body = render_email_html(new_rows)
    return {
        "ok": True,
        "dry_run": dry_run,
        "recipient": target,
        "subject": subject,
        "dashboard_summary": dashboard.get("summary") or {},
        "candidate_rows": len(rows),
        "new_count": len(new_rows),
        "skipped_already_sent": len(skipped),
        "sent": 0,
        "new_rows": new_rows,
        "skipped_rows": skipped,
        "text_body": text_body,
        "html_body": html_body,
    }


def email_alert_row(row: dict[str, Any]) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("eshidis_id") or row.get("official_id") or row.get("display_id") or "")
    official_url = official_url_for_row(row)
    return {
        "row_key": row_key,
        "display_id": row.get("display_id") or row.get("eshidis_id") or row.get("official_id"),
        "source_label": row.get("source_label"),
        "title": row.get("title"),
        "authority_name": row.get("authority_name"),
        "budget_display": row.get("budget_display"),
        "deadline_display": row.get("deadline_display"),
        "official_url": official_url,
    }


def official_url_for_row(row: dict[str, Any]) -> str | None:
    linked_ids = linked_eshidis_ids_for_row(row)
    eshidis_id = str(row.get("eshidis_id") or (linked_ids[0] if linked_ids else "") or "").strip()
    if eshidis_id:
        return f"https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{quote(eshidis_id)}"
    for key in ("official_url", "source_url", "attachment_url", "download_url"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return None


def render_email_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Δεν υπάρχουν νέα έργα για αποστολή."
    lines = ["Νέα έργα Tender Radar:", ""]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"{index}. {row.get('title') or ''}",
                f"Α/Α: {row.get('display_id') or ''}",
                f"Πηγή: {row.get('source_label') or ''}",
                f"Φορέας: {row.get('authority_name') or ''}",
                f"Προϋπολογισμός: {row.get('budget_display') or ''}",
                f"Λήξη: {row.get('deadline_display') or ''}",
                f"Link: {row.get('official_url') or ''}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def render_email_html(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>Δεν υπάρχουν νέα έργα για αποστολή.</p>"
    items = []
    for row in rows:
        link = row.get("official_url")
        title = escape_html(row.get("title") or "")
        title_html = f'<a href="{escape_html(link)}">{title}</a>' if link else title
        items.append(
            "<li>"
            f"<strong>{title_html}</strong><br>"
            f"Α/Α: {escape_html(row.get('display_id') or '')}<br>"
            f"Πηγή: {escape_html(row.get('source_label') or '')}<br>"
            f"Φορέας: {escape_html(row.get('authority_name') or '')}<br>"
            f"Προϋπολογισμός: {escape_html(row.get('budget_display') or '')}<br>"
            f"Λήξη: {escape_html(row.get('deadline_display') or '')}"
            "</li>"
        )
    return "<h2>Νέα έργα Tender Radar</h2><ol>" + "".join(items) + "</ol>"


def escape_html(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def email_alert_recipient() -> str | None:
    env = load_local_env()
    return (
        os.environ.get("ALERT_EMAIL_TO")
        or os.environ.get("EMAIL_ALERT_TO")
        or os.environ.get("EMAIL_TO")
        or env.get("ALERT_EMAIL_TO")
        or env.get("EMAIL_ALERT_TO")
        or env.get("EMAIL_TO")
    )


def smtp_config() -> dict[str, str]:
    env = load_local_env()
    keys = {
        "host": "SMTP_HOST",
        "port": "SMTP_PORT",
        "username": "SMTP_USERNAME",
        "password": "SMTP_PASSWORD",
        "from_email": "EMAIL_FROM",
    }
    config = {name: os.environ.get(env_key) or env.get(env_key) or "" for name, env_key in keys.items()}
    missing = [name for name, value in config.items() if not value]
    if missing:
        raise ValueError(f"SMTP is not configured: missing {', '.join(missing)}.")
    return config


def send_email_alert(recipient: str, subject: str, text_body: str, html_body: str) -> None:
    config = smtp_config()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_email"]
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    port = int(config["port"])
    with smtplib.SMTP(config["host"], port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config["username"], config["password"])
        smtp.send_message(message)


def load_local_env() -> dict[str, str]:
    path = REPO_ROOT / ".env.local"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def quick_source_fingerprint(*, timeout_seconds: int = 8) -> dict[str, Any]:
    config_path = REPO_ROOT / "config/sources.yml"
    config = load_config(config_path) if config_path.exists() else {}
    sources: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    entries = configured_source_entries(config)
    tasks = [
        (
            str(entry.get("id") or "unknown"),
            lambda entry=entry: _configured_source_fingerprint(entry, timeout_seconds=timeout_seconds),
        )
        for entry in entries
    ]
    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as executor:
        future_sources = {executor.submit(task): source_id for source_id, task in tasks}
        for future in as_completed(future_sources):
            source_id = future_sources[future]
            try:
                sources.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive network boundary
                errors.append({"source": source_id, "message": str(exc)})
    stable_sources = sorted(sources, key=lambda item: str(item.get("source_id") or ""))
    template_total = sum(1 for item in stable_sources if item.get("status") == "REQUIRES_IDENTIFIER")
    digest = hashlib.sha256(json.dumps(stable_sources, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "ok": not errors,
        "computed_at": utc_now_iso(),
        "hash": digest,
        "sources": stable_sources,
        "errors": errors,
        "source_count": {
            "configured_total": len(entries),
            "attempted_total": len(entries) - template_total,
            "reached_total": sum(1 for item in stable_sources if item.get("reachable") is True),
            "template_total": template_total,
            "error_total": len(errors),
        },
        "status_note": "Cheap source fingerprint; unchanged means expensive discovery can reuse cached reports.",
    }


def configured_source_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for source in config.get("global_sources") or []:
        if isinstance(source, dict):
            entries.append({**source, "source_group": "global_sources"})
    for source in config.get("authority_adapters") or []:
        if isinstance(source, dict):
            entries.append({**source, "source_group": "authority_adapters"})
    return entries


def _configured_source_fingerprint(source: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    source_group = str(source.get("source_group") or "")
    source_type = str(source.get("type") or "")
    source_id = str(source.get("id") or "")
    if source_type == "url_template":
        return {
            "source_id": source.get("id"),
            "source_group": source_group,
            "adapter": source_type,
            "url": source.get("url"),
            "status": "REQUIRES_IDENTIFIER",
            "attempted": False,
            "reachable": None,
            "token": source.get("url"),
        }
    if source_id == "eshidis_active_search":
        cached = _eshidis_active_report_fingerprint(source)
        if cached is not None:
            return cached
    if source_group == "global_sources":
        if source_type == "api_post":
            return _kimdis_global_fingerprint(source, timeout_seconds=timeout_seconds)
        return _html_source_fingerprint(source, timeout_seconds=timeout_seconds)
    return _authority_source_fingerprint(source, timeout_seconds=timeout_seconds)


def _eshidis_active_report_fingerprint(source: dict[str, Any]) -> dict[str, Any] | None:
    path = REPO_ROOT / "work/reports/eshidis_active_candidates.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    candidates = [candidate for candidate in payload.get("candidates") or [] if isinstance(candidate, dict)]
    stable_candidates = [
        {
            "eshidis_id": candidate.get("eshidis_id"),
            "title": candidate.get("title"),
            "authority": candidate.get("authority"),
            "deadline": candidate.get("submission_deadline"),
            "published_at": candidate.get("published_at"),
        }
        for candidate in candidates[:25]
    ]
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    token_payload = {
        "candidate_status": payload.get("candidate_status"),
        "top_candidates": stable_candidates,
        "candidates_found": coverage.get("candidates_found"),
    }
    token = hashlib.sha256(json.dumps(token_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "source_id": source.get("id"),
        "source_group": source.get("source_group"),
        "adapter": source.get("type") or source.get("adapter") or "web_app",
        "url": source.get("url"),
        "status": "CACHED_DISCOVERY_WATERMARK",
        "attempted": False,
        "reachable": True,
        "token": token,
        "count_hint": len(candidates),
    }


def _kimdis_global_fingerprint(source: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    url = str(source.get("url") or "").replace("{PAGE}", "0")
    body: dict[str, Any] = {}
    if source.get("contract_type"):
        body["contractType"] = str(source.get("contract_type"))
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "TenderRadar/0.1 source-preflight"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    content = payload.get("content") if isinstance(payload.get("content"), list) else []
    first = content[0] if content and isinstance(content[0], dict) else {}
    return {
        "source_id": source.get("id"),
        "source_group": source.get("source_group"),
        "adapter": "api_post",
        "url": url,
        "status": "REACHED",
        "attempted": True,
        "reachable": True,
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
        "source_group": source.get("source_group"),
        "adapter": source.get("adapter"),
        "url": url,
        "status": "REACHED",
        "attempted": True,
        "reachable": True,
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
        "source_group": source.get("source_group"),
        "adapter": source.get("adapter"),
        "status": "REACHED",
        "attempted": True,
        "reachable": True,
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
        "source_group": source.get("source_group"),
        "adapter": source.get("adapter"),
        "url": url,
        "status": "REACHED",
        "attempted": True,
        "reachable": True,
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
    source_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
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
    if source_preflight is not None:
        payload["source_preflight"] = source_preflight
    return payload


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
    selective_capable_ids = selective_source_ids_from_config()
    selective_refresh = (
        selective
        and has_previous_baseline
        and bool(changed_source_ids)
        and changed_source_ids <= selective_capable_ids
    )
    should_refresh_eshidis = (not selective_refresh) or "eshidis_active_search" in changed_source_ids
    if should_refresh_eshidis:
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
        changed_kimdis_source_ids = sorted(source_id for source_id in changed_source_ids if source_id in kimdis_selective_source_ids())
        authority_source_ids = sorted(source_id for source_id in changed_source_ids if source_id in authority_source_ids_from_config())
        if not changed_kimdis_source_ids:
            expanded_args.extend(["--kimdis-source-id", "__none__"])
        else:
            for source_id in changed_kimdis_source_ids:
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


def selective_source_ids_from_config() -> set[str]:
    return {"eshidis_active_search"} | kimdis_selective_source_ids() | authority_source_ids_from_config()


def kimdis_selective_source_ids() -> set[str]:
    return {"khmdhs_notice", "khmdhs_auction", "khmdhs_contract"}


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
    overrides = triage_overrides_by_key()
    force_keep_keys = {key for key, item in overrides.items() if item.get("action") == "FORCE_KEEP"}
    ignored = ignored_tender_keys() - force_keep_keys
    triage = ai_triage_by_row_key() if apply_triage else {}
    rows = merged_tender_rows()
    rows = [row for row in rows if str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "") not in ignored]
    rows = [attach_ai_triage(row, triage, overrides=overrides) for row in rows]
    rows = [row_with_document_evidence(row) for row in rows]
    canonical_rows, duplicate_hidden_rows = suppress_linked_eshidis_duplicates(rows)
    official_deadlines = official_eshidis_deadlines_by_id(canonical_rows)
    active_rows = [
        row
        for row in canonical_rows
        if dashboard_row_is_active(row, as_of=as_of, official_deadlines=official_deadlines)
    ]
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
    canonical_eshidis_ids = canonical_eshidis_ids_in_rows(rows)
    canonical_by_eshidis_id = {
        str(row.get("eshidis_id") or row.get("display_id") or "").strip(): row
        for row in rows
        if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ"
        and str(row.get("eshidis_id") or row.get("display_id") or "").strip() in canonical_eshidis_ids
    }
    verified_by_source = verified_eshidis_links_by_source_key()
    verified_by_target = verified_eshidis_links_by_target_id(verified_by_source)
    kept: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    for row in rows:
        source_label = str(row.get("source_label") or "")
        row_key = row_key_for_tender(row)
        if source_label == "ΕΣΗΔΗΣ":
            eshidis_id = str(row.get("eshidis_id") or row.get("display_id") or "").strip()
            kept.append(
                {
                    **row,
                    "verified_source_links": verified_by_target.get(eshidis_id, []),
                    "verified_eshidis_link_status": "OFFICIAL_ESHIDIS_ROW",
                }
            )
            continue
        verified_links = verified_by_source.get(row_key, [])
        verified_ids = sorted(
            {
                str(link.get("target_eshidis_id") or "")
                for link in verified_links
                if str(link.get("target_eshidis_id") or "").isdigit()
            }
        )
        verified_duplicate_ids = sorted(canonical_eshidis_ids & set(verified_ids))
        strong_duplicate_ids = sorted(
            eshidis_id
            for eshidis_id in canonical_eshidis_ids & set(linked_eshidis_ids_for_row(row))
            if eshidis_id not in verified_duplicate_ids
            and strong_linked_eshidis_duplicate(row, canonical_by_eshidis_id.get(eshidis_id))
        )
        duplicate_ids = [*verified_duplicate_ids, *strong_duplicate_ids]
        if duplicate_ids:
            is_verified_duplicate = bool(verified_duplicate_ids)
            hidden.append(
                {
                    **row,
                    "duplicate_hidden": True,
                    "duplicate_reason": (
                        f"Verified duplicate of ESHIDIS {', '.join(verified_duplicate_ids)}"
                        if is_verified_duplicate
                        else f"Strong linked duplicate of ESHIDIS {', '.join(strong_duplicate_ids)}"
                    ),
                    "verified_eshidis_ids": duplicate_ids,
                    "verified_eshidis_links": verified_links,
                    "verified_eshidis_link_status": (
                        "REPLACED_BY_OFFICIAL_ESHIDIS"
                        if is_verified_duplicate
                        else "STRONG_LINKED_ESHIDIS_DUPLICATE"
                    ),
                }
            )
            continue
        if verified_ids:
            kept.append(
                {
                    **row,
                    "verified_eshidis_ids": verified_ids,
                    "verified_eshidis_links": verified_links,
                    "verified_eshidis_link_status": "VERIFIED_ESHIDIS_LINK_PENDING_OFFICIAL_ROW",
                }
            )
            continue
        kept.append(
            {
                **row,
                "verified_eshidis_ids": [],
                "verified_eshidis_links": [],
                "verified_eshidis_link_status": "NO_VERIFIED_ESHIDIS_LINK",
            }
        )
    return kept, hidden


def strong_linked_eshidis_duplicate(row: dict[str, Any], official_row: dict[str, Any] | None) -> bool:
    if not official_row:
        return False
    matches: list[str] = []
    row_title = normalized_duplicate_text(row.get("title"))
    official_title = normalized_duplicate_text(official_row.get("title"))
    if row_title and official_title and row_title == official_title:
        matches.append("title")
    row_deadline = deadline_sort_key(str(row.get("current_deadline_at") or row.get("submission_deadline") or ""))
    official_deadline = deadline_sort_key(str(official_row.get("current_deadline_at") or official_row.get("submission_deadline") or ""))
    if row_deadline != "9999" and official_deadline != "9999" and row_deadline == official_deadline:
        matches.append("deadline")
    row_budget = budget_sort_value(row.get("budget_with_vat") or row.get("budget_without_vat") or row.get("budget"))
    official_budget = budget_sort_value(
        official_row.get("budget_with_vat") or official_row.get("budget_without_vat") or official_row.get("budget")
    )
    if row_budget is not None and official_budget is not None and abs(row_budget - official_budget) <= 1:
        matches.append("budget")
    row_authority = normalized_duplicate_text(row.get("authority_name") or row.get("authority"))
    official_authority = normalized_duplicate_text(official_row.get("authority_name") or official_row.get("authority"))
    if row_authority and official_authority and (row_authority in official_authority or official_authority in row_authority):
        matches.append("authority")
    return len(matches) >= 2


def normalized_duplicate_text(value: object) -> str:
    return normalize_greek(str(value or "")).replace("ς", "σ")


def verified_eshidis_links_by_source_key() -> dict[str, list[dict[str, Any]]]:
    try:
        links = list_verified_tender_links(runtime_db_path())
    except (OSError, sqlite3.Error):
        return {}
    by_source: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        payload = {
            "source_row_key": link.source_row_key,
            "source_identifier": link.source_identifier,
            "source_label": link.source_label,
            "source_url": link.source_url,
            "target_eshidis_id": link.target_eshidis_id,
            "target_tender_id": link.target_tender_id,
            "verification_status": link.verification_status,
            "verified_at": link.verified_at,
            "source_signature": link.source_signature,
            "evidence": link.evidence,
        }
        by_source.setdefault(link.source_row_key, []).append(payload)
    return by_source


def verified_eshidis_links_by_target_id(
    by_source: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    by_source = by_source if by_source is not None else verified_eshidis_links_by_source_key()
    by_target: dict[str, list[dict[str, Any]]] = {}
    for links in by_source.values():
        for link in links:
            target = str(link.get("target_eshidis_id") or "")
            if target:
                by_target.setdefault(target, []).append(link)
    return by_target


def linked_eshidis_enrichment_steps() -> list[dict[str, Any]]:
    return official_eshidis_fetch_steps(linked_eshidis_ids_missing_official_rows(merged_tender_rows()))


def run_linked_eshidis_enrichment() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    missing_ids = linked_eshidis_ids_missing_official_rows(merged_tender_rows())
    attempted = linked_eshidis_fetch_attempts()
    skipped_ids = [eshidis_id for eshidis_id in missing_ids if eshidis_id in attempted]
    fetch_ids = [eshidis_id for eshidis_id in missing_ids if eshidis_id not in attempted]
    results: list[dict[str, Any]] = []
    attempt_records: list[dict[str, Any]] = []
    for eshidis_id in fetch_ids:
        id_results: list[dict[str, Any]] = []
        for step in official_eshidis_fetch_steps([eshidis_id]):
            result = run_cli_process(step["args"], timeout=int(step["timeout"]))
            result["name"] = step["name"]
            id_results.append(result)
            results.append(result)
            if result.get("returncode") != 0:
                break
        attempt_records.append(
            {
                "eshidis_id": eshidis_id,
                "attempted_at": utc_now_iso(),
                "ok": bool(id_results) and all(item.get("returncode") == 0 for item in id_results),
                "steps": [
                    {"name": item.get("name"), "returncode": item.get("returncode")}
                    for item in id_results
                ],
            }
        )
    if attempt_records:
        write_linked_eshidis_fetch_attempts(attempt_records)
    canonical_after = canonical_eshidis_ids_in_rows(merged_tender_rows())
    enriched_ids = sorted({eshidis_id for eshidis_id in fetch_ids if eshidis_id in canonical_after})
    failed_ids = sorted(set(fetch_ids) - set(enriched_ids))
    return results, {
        "missing_before": missing_ids,
        "attempted": fetch_ids,
        "enriched": enriched_ids,
        "failed": failed_ids,
        "skipped_previously_attempted": skipped_ids,
    }


def linked_eshidis_fetch_attempts_path() -> Path:
    return REPO_ROOT / "work/derived/linked_eshidis_fetch_attempts.json"


def linked_eshidis_fetch_attempts() -> dict[str, dict[str, Any]]:
    path = linked_eshidis_fetch_attempts_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    attempts: dict[str, dict[str, Any]] = {}
    for item in payload.get("attempts") or []:
        if not isinstance(item, dict):
            continue
        eshidis_id = str(item.get("eshidis_id") or "").strip()
        if eshidis_id.isdigit():
            attempts[eshidis_id] = item
    return attempts


def write_linked_eshidis_fetch_attempts(attempt_records: list[dict[str, Any]]) -> None:
    path = linked_eshidis_fetch_attempts_path()
    existing = linked_eshidis_fetch_attempts()
    for item in attempt_records:
        eshidis_id = str(item.get("eshidis_id") or "").strip()
        if eshidis_id:
            existing[eshidis_id] = item
    payload = {"updated_at": utc_now_iso(), "attempts": list(existing.values())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def linked_eshidis_ids_missing_official_rows(rows: list[dict[str, Any]]) -> list[str]:
    linked_ids: set[str] = set()
    for row in rows:
        if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ":
            continue
        linked_ids.update(linked_eshidis_ids_for_row(row))
    return sorted(linked_ids - canonical_eshidis_ids_in_rows(rows))


def canonical_eshidis_ids_in_rows(rows: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        eshidis_id = str(row.get("eshidis_id") or row.get("display_id") or "").strip()
        if not eshidis_id.isdigit() or str(row.get("source_label") or "") != "ΕΣΗΔΗΣ":
            continue
        source = str(row.get("source") or "")
        if source != "sqlite" or row.get("current_deadline_at"):
            ids.add(eshidis_id)
    return ids


def linked_eshidis_ids_for_row(row: dict[str, Any]) -> list[str]:
    values = [str(value) for value in row.get("linked_eshidis_ids") or [] if str(value).strip()]
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    values.extend(str(value) for value in ai.get("eshidis_id_candidates") or [] if str(value).strip())
    return sorted({value for value in values if value.isdigit()})


def ai_triage_report_path() -> Path:
    return REPO_ROOT / "work/reports/ai_triage_report.json"


def ai_triage_report_status() -> dict[str, Any]:
    path = ai_triage_report_path()
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"exists": True, "path": str(path), "ok": False, "error": str(exc)}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "exists": True,
        "ok": int(summary.get("errors") or 0) == 0,
        "path": str(path),
        "markdown_path": str(REPO_ROOT / "work/reports/ai_triage_report.md"),
        "generated_at": payload.get("generated_at"),
        "model": payload.get("model"),
        "input_rows": payload.get("input_rows"),
        "summary": summary,
    }


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


def row_key_for_tender(row: dict[str, Any]) -> str:
    return str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "")


def triage_overrides_by_key() -> dict[str, dict[str, object]]:
    try:
        return db_triage_overrides_by_key(runtime_db_path())
    except (OSError, sqlite3.Error):
        return {}


def attach_ai_triage(
    row: dict[str, Any],
    triage: dict[str, dict[str, Any]],
    *,
    overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "")
    ai = triage.get(row_key)
    override = (overrides or {}).get(row_key)
    override_action = str((override or {}).get("action") or "")
    if not ai:
        return {**row, "ai_triage": None, "ai_triage_hidden": False, "triage_override": override}
    keep = bool(ai.get("keep_for_daily_review"))
    if override_action == "FORCE_KEEP":
        keep = True
    return {
        **row,
        "ai_triage": {
            "decision": ai.get("decision"),
            "confidence": ai.get("confidence"),
            "reason": ai.get("reason"),
            "eshidis_id_candidates": ai.get("eshidis_id_candidates") or [],
        },
        "ai_triage_hidden": not keep,
        "triage_override": override,
    }


def ignored_tenders_path() -> Path:
    return REPO_ROOT / "work/derived/ignored_tenders.json"


def ignored_tender_keys() -> set[str]:
    keys = set()
    try:
        keys.update(ignored_tender_keys_from_db(runtime_db_path()))
    except (OSError, sqlite3.Error):
        pass
    path = ignored_tenders_path()
    if not path.exists():
        return keys
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return keys
    keys.update(str(item.get("row_key") or "") for item in payload.get("ignored") or [] if isinstance(item, dict))
    return {key for key in keys if key}


def dismiss_tender(row_key: str) -> dict[str, Any]:
    dismiss_tender_in_db(runtime_db_path(), row_key=row_key)
    path = ignored_tenders_path()
    existing = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        existing = [item for item in payload.get("ignored") or [] if isinstance(item, dict)]
    if not any(item.get("row_key") == row_key for item in existing):
        existing.append({"row_key": row_key, "ignored_at": utc_now_iso()})
    payload = {"updated_at": utc_now_iso(), "ignored": existing}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "row_key": row_key, "ignored": len(existing), "dashboard": dashboard_payload(scope="focus")}


def remove_legacy_ignored_tender(row_key: str) -> None:
    path = ignored_tenders_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    existing = [item for item in payload.get("ignored") or [] if isinstance(item, dict) and item.get("row_key") != row_key]
    payload = {"updated_at": utc_now_iso(), "ignored": existing}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def restore_admin_row(*, row_key: str, reason: str | None = None) -> dict[str, Any]:
    remove_tender_dismissal(runtime_db_path(), row_key=row_key)
    remove_legacy_ignored_tender(row_key)
    upsert_triage_override(
        runtime_db_path(),
        row_key=row_key,
        action="FORCE_KEEP",
        reason=reason,
        metadata={"source": "admin_panel"},
    )
    return {"ok": True, "row_key": row_key, "dashboard": dashboard_payload(scope="focus"), "admin": admin_audit_payload()}


def admin_password() -> str | None:
    env = load_local_env()
    value = (
        os.environ.get("TENDER_RADAR_ADMIN_PASSWORD")
        or os.environ.get("ADMIN_PASSWORD")
        or env.get("TENDER_RADAR_ADMIN_PASSWORD")
        or env.get("ADMIN_PASSWORD")
    )
    return value or None


def admin_login_email() -> str | None:
    env = load_local_env()
    value = (
        os.environ.get("TENDER_RADAR_ADMIN_EMAIL")
        or os.environ.get("ADMIN_EMAIL")
        or env.get("TENDER_RADAR_ADMIN_EMAIL")
        or env.get("ADMIN_EMAIL")
        or email_alert_recipient()
    )
    return value.strip().lower() if value else None


def admin_status_payload() -> dict[str, Any]:
    users = list_admin_users(runtime_db_path())
    return {
        "admin_enabled": bool(admin_password() or admin_login_email() or users),
        "email_login_enabled": bool(admin_login_email()),
        "password_users": len([user for user in users if user.password_hash and user.enabled]),
    }


def auth_status_payload(session: dict[str, str] | None) -> dict[str, Any]:
    if not session:
        return {"ok": True, "authenticated": False, "session": None, "admin": admin_status_payload()}
    return {
        "ok": True,
        "authenticated": True,
        "session": {"email": session.get("email"), "role": session.get("role")},
        "admin": admin_status_payload(),
    }


def request_admin_login_code(payload: dict[str, Any]) -> dict[str, Any]:
    requested_email = str(payload.get("email") or "").strip().lower()
    allowed_email = admin_login_email()
    if not allowed_email:
        raise ValueError("Admin email login is not configured.")
    if requested_email != allowed_email:
        raise ValueError("This email is not allowed for admin login.")
    code = f"{secrets.randbelow(900000) + 100000}"
    with ADMIN_LOGIN_CODES_LOCK:
        ADMIN_LOGIN_CODES[requested_email] = {"code": code, "expires_at": time.time() + 600}
    send_email_alert(
        requested_email,
        "Tender Radar admin login code",
        f"Ο κωδικός σύνδεσης Tender Radar είναι: {code}\nΙσχύει για 10 λεπτά.",
        f"<p>Ο κωδικός σύνδεσης Tender Radar είναι:</p><h2>{code}</h2><p>Ισχύει για 10 λεπτά.</p>",
    )
    return {"ok": True, "sent": True, "email": requested_email}


def verify_admin_login_code(*, email: str, code: str) -> bool:
    if not email or not code:
        return False
    with ADMIN_LOGIN_CODES_LOCK:
        record = ADMIN_LOGIN_CODES.get(email)
        if not record:
            return False
        if time.time() > float(record.get("expires_at") or 0):
            ADMIN_LOGIN_CODES.pop(email, None)
            return False
        if not secrets.compare_digest(str(record.get("code") or ""), code):
            return False
        ADMIN_LOGIN_CODES.pop(email, None)
    return True


def public_base_url() -> str | None:
    env = load_local_env()
    value = os.environ.get("TENDER_RADAR_PUBLIC_URL") or env.get("TENDER_RADAR_PUBLIC_URL")
    return value.rstrip("/") if value else None


def ensure_owner_admin_user(email: str) -> None:
    if not email:
        return
    existing = get_admin_user(runtime_db_path(), email)
    if not existing:
        upsert_admin_user(runtime_db_path(), email=email, role="admin", enabled=True)


def request_admin_password_setup(payload: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    requested_email = str(payload.get("email") or "").strip().lower()
    allowed_email = admin_login_email()
    if not allowed_email:
        raise ValueError("Admin email is not configured.")
    if requested_email != allowed_email:
        raise ValueError("This email is not allowed for owner password setup.")
    ensure_owner_admin_user(requested_email)
    token, link = create_password_setup_invite(email=requested_email, role="admin", created_by="owner-bootstrap", base_url=base_url)
    send_password_setup_email(requested_email, link, role="admin")
    return {"ok": True, "sent": True, "email": requested_email, "role": "admin", "token_preview": token[:6]}


def invite_admin_user(payload: dict[str, Any], *, inviter: str | None, base_url: str) -> dict[str, Any]:
    email = str(payload.get("email") or "").strip().lower()
    role = str(payload.get("role") or "user").strip().lower()
    if role not in {"user", "admin"}:
        raise ValueError("Role must be user or admin.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Valid email is required.")
    token, link = create_password_setup_invite(email=email, role=role, created_by=inviter, base_url=base_url)
    send_password_setup_email(email, link, role=role)
    return {"ok": True, "sent": True, "email": email, "role": role, "token_preview": token[:6], "users": admin_users_payload()["users"]}


def create_password_setup_invite(*, email: str, role: str, created_by: str | None, base_url: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hash_reset_token(token)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    upsert_admin_user(runtime_db_path(), email=email, role=role, enabled=True)
    create_admin_invite(
        runtime_db_path(),
        token_hash=token_hash,
        email=email,
        role=role,
        created_by=created_by,
        expires_at=expires_at,
    )
    return token, f"{base_url}/password-setup?token={quote(token)}"


def send_password_setup_email(email: str, link: str, *, role: str) -> None:
    role_label = "διαχειριστής" if role == "admin" else "χρήστης"
    text_body = (
        "Έχεις πρόσκληση στο Tender Radar.\n\n"
        f"Ρόλος: {role_label}\n"
        f"Όρισε password από εδώ: {link}\n\n"
        "Το link ισχύει για 24 ώρες."
    )
    html_body = (
        "<p>Έχεις πρόσκληση στο <strong>Tender Radar</strong>.</p>"
        f"<p>Ρόλος: <strong>{role_label}</strong></p>"
        f"<p><a href=\"{link}\">Ορισμός password</a></p>"
        "<p>Το link ισχύει για 24 ώρες.</p>"
    )
    send_email_alert(email, "Tender Radar πρόσκληση σύνδεσης", text_body, html_body)


def complete_admin_password_setup(*, token: str, password: str) -> dict[str, str]:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    invite = get_admin_invite(runtime_db_path(), hash_reset_token(token))
    if not invite:
        raise ValueError("Invalid password setup link.")
    if invite.used_at:
        raise ValueError("Password setup link has already been used.")
    expires_at = datetime.fromisoformat(invite.expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise ValueError("Password setup link has expired.")
    password_hash = hash_password(password)
    user = upsert_admin_user(
        runtime_db_path(),
        email=invite.email,
        role=invite.role,
        password_hash=password_hash,
        enabled=True,
        mark_accepted=True,
    )
    mark_admin_invite_used(runtime_db_path(), invite.token_hash)
    return {"email": user.email, "role": user.role}


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str, *, iterations: int = 260000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_text))
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def verify_admin_user_password(*, email: str, password: str) -> bool:
    user = get_admin_user(runtime_db_path(), email)
    if not user or not user.enabled:
        return False
    if user.role != "admin":
        return False
    return verify_password(password, user.password_hash)


def admin_users_payload() -> dict[str, Any]:
    users = []
    for user in list_admin_users(runtime_db_path()):
        users.append(
            {
                "email": user.email,
                "role": user.role,
                "enabled": user.enabled,
                "invited_at": user.invited_at,
                "accepted_at": user.accepted_at,
                "password_set": bool(user.password_hash),
                "password_set_at": user.password_set_at,
                "last_login_at": user.last_login_at,
            }
        )
    return {"ok": True, "users": users}


def admin_audit_payload() -> dict[str, Any]:
    overrides = triage_overrides_by_key()
    force_keep_keys = {key for key, item in overrides.items() if item.get("action") == "FORCE_KEEP"}
    ignored_keys = ignored_tender_keys() - force_keep_keys
    triage = ai_triage_by_row_key()
    rows = [attach_ai_triage(row, triage, overrides=overrides) for row in merged_tender_rows()]
    row_by_key = {row_key_for_tender(row): row for row in rows if row_key_for_tender(row)}

    dismissed_rows = []
    for item in list_tender_dismissals(runtime_db_path()):
        row_key = str(item.get("row_key") or "")
        if row_key in force_keep_keys:
            continue
        row = row_by_key.get(row_key, {})
        dismissed_rows.append(
            admin_hidden_row(
                row or item,
                category="DISMISSED",
                reason=str(item.get("reason") or "Χειροκίνητη επιλογή: Δεν με ενδιαφέρει"),
                restorable=True,
            )
        )

    triage_hidden_rows = [
        admin_hidden_row(
            row,
            category="AI_HIDDEN",
            reason=str(((row.get("ai_triage") or {}).get("reason")) or "AI triage marked this row as not for daily review."),
            restorable=True,
        )
        for row in rows
        if row_key_for_tender(row) not in ignored_keys and row.get("ai_triage_hidden")
    ]

    active_source_rows = [row for row in rows if row_key_for_tender(row) not in ignored_keys]
    canonical_rows, duplicate_rows = suppress_linked_eshidis_duplicates(active_source_rows)
    official_deadlines = official_eshidis_deadlines_by_id(canonical_rows)
    expired_rows = [row for row in canonical_rows if not dashboard_row_is_active(row, official_deadlines=official_deadlines)]
    duplicate_hidden_rows = [
        admin_hidden_row(
            row,
            category="DUPLICATE",
            reason=str(row.get("duplicate_reason") or "Κρύφτηκε επειδή υπάρχει canonical ΕΣΗΔΗΣ εγγραφή."),
            restorable=False,
        )
        for row in duplicate_rows
    ]
    expired_hidden_rows = [
        admin_hidden_row(
            row,
            category="EXPIRED",
            reason="Κρύφτηκε επειδή η προθεσμία δεν είναι μεταγενέστερη της σημερινής ημερομηνίας.",
            restorable=False,
        )
        for row in expired_rows
    ]
    source_errors = source_polling_payload().get("rows") or []
    errors = [
        {
            "source_id": row.get("source_id"),
            "name": row.get("name"),
            "error": row.get("last_error"),
            "last_checked_at": row.get("last_checked_at"),
        }
        for row in source_errors
        if row.get("last_error")
    ]
    hidden_rows = dismissed_rows + triage_hidden_rows + duplicate_hidden_rows + expired_hidden_rows
    return {
        "ok": True,
        "authenticated": True,
        "summary": {
            "hidden_total": len(hidden_rows),
            "dismissed": len(dismissed_rows),
            "ai_hidden": len(triage_hidden_rows),
            "duplicates": len(duplicate_hidden_rows),
            "expired": len(expired_hidden_rows),
            "source_errors": len(errors),
            "manual_force_keep": len(force_keep_keys),
        },
        "hidden_rows": hidden_rows,
        "source_errors": errors,
    }


def admin_hidden_row(row: dict[str, Any], *, category: str, reason: str, restorable: bool) -> dict[str, Any]:
    row_key = row_key_for_tender(row) or str(row.get("row_key") or "")
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    return {
        "row_key": row_key,
        "category": category,
        "restorable": restorable,
        "display_id": row.get("display_id") or row.get("eshidis_id") or row.get("official_id") or "",
        "source_label": row.get("source_label") or "",
        "title": row.get("title") or "",
        "authority_name": row.get("authority_name") or row.get("authority") or "",
        "deadline_display": row.get("deadline_display") or row.get("current_deadline_at") or "",
        "official_url": row.get("official_url") or row.get("source_url") or row.get("attachment_url") or "",
        "reason": reason,
        "ai_decision": ai.get("decision"),
        "ai_confidence": ai.get("confidence"),
    }


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
        if non_tender_landing_row(candidate):
            continue
        public_works_gate = public_works_gate_for_candidate(candidate)
        if not public_works_gate.get("keep_for_daily_search"):
            continue
        official_id = str(candidate.get("official_id") or "").strip()
        record_type = str(candidate.get("record_type") or "")
        if not official_id:
            continue
        is_kimdis = is_kimdis_identifier(official_id)
        is_eshidis = authority_numeric_id_is_eshidis(official_id, candidate)
        row_key = f"KIMDIS:{official_id}" if is_kimdis else official_id if is_eshidis else f"AUTHORITY:{official_id}"
        authority_docs = authority_documents_by_key().get(row_key, [])
        attachment_urls = [str(url) for url in candidate.get("attachment_urls") or [] if str(url).strip()]
        if not attachment_urls and candidate.get("attachment_url"):
            attachment_urls = [str(candidate.get("attachment_url"))]
        linked_eshidis_ids = sorted(
            {
                *extract_eshidis_ids_from_text(
                    candidate.get("title"),
                    candidate.get("source_url"),
                    candidate.get("detail_url"),
                    candidate.get("attachment_url"),
                    " ".join(attachment_urls),
                    candidate.get("row_text"),
                ),
                *authority_linked_eshidis_ids(row_key, documents=authority_docs),
            }
        )
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
                    for key in (
                        "title",
                        "authority",
                        "published_at",
                        "source_url",
                        "detail_url",
                        "attachment_url",
                        "matched_scopes",
                        "match_notes",
                        "row_text",
                    )
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
                "linked_eshidis_ids": linked_eshidis_ids,
                "public_works_gate": public_works_gate,
                "interest_match": bool(candidate.get("matched_scopes")),
                "interest_reason": ", ".join([*(candidate.get("matched_scopes") or []), *(candidate.get("match_notes") or [])]),
                "authority_record_type": record_type,
            }
        )
    return rows


def non_tender_landing_row(row: dict[str, Any]) -> bool:
    title = normalize_greek(str(row.get("title") or ""))
    url = str(row.get("source_url") or row.get("official_url") or row.get("detail_url") or "").casefold().rstrip("/")
    if url.endswith("/erga-drasis"):
        return True
    return title in {"εργα & δρασεις", "εργα και δρασεις"}


def authority_numeric_id_is_eshidis(official_id: str, candidate: dict[str, Any]) -> bool:
    if not official_id.isdigit() or len(official_id) != 6:
        return False
    haystack = normalize_greek(
        " ".join(
            str(candidate.get(key) or "")
            for key in ("source_url", "detail_url", "attachment_url", "row_text", "title")
        )
    )
    if any(host in haystack for host in ("ted europa eu", "ted.europa.eu")) and not any(
        marker in haystack for marker in ("εσηδης", "ε.σ.η.δη.σ", "actsearchergwn")
    ):
        return False
    record_type = normalize_greek(str(candidate.get("record_type") or ""))
    if record_type == "eshidis":
        return True
    return any(
        marker in haystack
        for marker in (
            "εσηδης",
            "ε.σ.η.δη.σ",
            "ε σ η δ η σ",
            "pwgopendata eprocurement gov gr",
            "actsearchergwn",
        )
    )


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


def authority_linked_eshidis_ids(row_key: str, *, documents: list[dict[str, Any]] | None = None) -> list[str]:
    values: list[str] = []
    for document in documents if documents is not None else authority_documents_by_key().get(row_key, []):
        if not isinstance(document, dict):
            continue
        values.extend(str(value) for value in document.get("linked_eshidis_ids") or [] if str(value).strip())
    return list(dict.fromkeys(values))


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
    request = Request(url_with_encoded_path(url), headers={"User-Agent": "TenderRadar/0.1 authority-document-fetch"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
    name = safe_filename(unquote(Path(urlparse(url).path).name or f"document_{index + 1}.bin"))
    path = target_dir / unique_archive_name(name, {item.name for item in target_dir.iterdir() if item.is_file()})
    path.write_bytes(body)
    return path, len(body)


def url_with_encoded_path(url: str) -> str:
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.netloc, quote(unquote(parts.path), safe="/%"), parts.query, parts.fragment))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kimdis_open_proc_rows() -> list[dict[str, Any]]:
    payload = expanded_report_payload()
    document_index = kimdis_documents_by_official_id()
    rows = []
    for candidate in payload.get("focus_open_proc_candidates", []):
        if not isinstance(candidate, dict):
            continue
        public_works_gate = public_works_gate_for_candidate(candidate)
        if not public_works_gate.get("keep_for_daily_search"):
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
                "public_works_gate": public_works_gate,
                "supports_eshidis_actions": False,
                "supports_kimdis_actions": True,
                "interest_match": bool(matched_scopes),
                "interest_reason": ", ".join([*matched_scopes, *match_notes]),
            }
        )
    return rows


def public_works_gate_for_candidate(candidate: dict[str, Any]) -> dict[str, object]:
    gate = candidate.get("public_works_gate") if isinstance(candidate.get("public_works_gate"), dict) else None
    if gate and "keep_for_daily_search" in gate:
        return gate
    return classify_public_works_candidate_dict(candidate)


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
    linked_ids = [str(value) for value in row.get("linked_eshidis_ids") or [] if str(value).strip()]
    text = " ".join(
        str(row.get(key) or "")
        for key in ("title", "authority_name", "region", "row_text")
    )
    official_status = "OFFICIAL_ESHIDIS" if eshidis_id else "LINKED_TO_ESHIDIS" if linked_ids else "CANDIDATE_NO_ESHIDIS_ID"
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
        "official_status": row.get("official_status") or official_status,
        "official_status_label": official_status_label(str(row.get("official_status") or official_status)),
        "verified_active": False,
    }


def official_status_label(status: str) -> str:
    labels = {
        "OFFICIAL_ESHIDIS": "Επίσημο ΕΣΗΔΗΣ",
        "LINKED_TO_ESHIDIS": "Σύνδεση με ΕΣΗΔΗΣ",
        "CANDIDATE_NO_ESHIDIS_ID": "Δεν βρέθηκε ακόμα ΕΣΗΔΗΣ",
    }
    return labels.get(status, status or "Άγνωστο")


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
                "sha256": document.get("sha256"),
                "source_url": document.get("attachment_url"),
                "text_sample": short_text_sample(
                    _none_or_str(
                        (document.get("document_analysis") or {}).get("text_sample")
                        if isinstance(document.get("document_analysis"), dict)
                        else None
                    )
                ),
                "view_url": f"/api/authority-document-file?row_key={row_key}&index={index}" if local_path else document.get("attachment_url"),
            }
        )
    linked_eshidis_ids = authority_linked_eshidis_ids(row_key, documents=documents)
    linked_eshidis_file_count = sum(len(eshidis_document_paths(eshidis_id)) for eshidis_id in linked_eshidis_ids)
    return {
        "row_key": row_key,
        "source_label": "Φορέας",
        "official_url": row.get("official_url") or row.get("attachment_url"),
        "candidate_status": row.get("status"),
        "official_status": "LINKED_TO_ESHIDIS" if linked_eshidis_ids else "NO_ESHIDIS_ID_FOUND",
        "linked_eshidis_ids": linked_eshidis_ids,
        "linked_eshidis_file_count": linked_eshidis_file_count,
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


def dashboard_row_is_active(
    row: dict[str, Any],
    *,
    as_of: date | None = None,
    official_deadlines: dict[str, str] | None = None,
) -> bool:
    deadline = deadline_date(str(row.get("current_deadline_at") or row.get("submission_deadline") or ""))
    if deadline is None and official_deadlines:
        linked_deadlines = [
            deadline_date(official_deadlines[eshidis_id])
            for eshidis_id in linked_eshidis_ids_for_row(row)
            if eshidis_id in official_deadlines
        ]
        linked_deadlines = [value for value in linked_deadlines if value is not None]
        if linked_deadlines:
            deadline = max(linked_deadlines)
    if deadline is None:
        deadline = deadline_date(str((row.get("deadline_evidence") or {}).get("deadline_at") or ""))
    if deadline is None:
        return False
    return deadline >= (as_of or date.today())


def official_eshidis_deadlines_by_id(rows: list[dict[str, Any]]) -> dict[str, str]:
    deadlines: dict[str, str] = {}
    for row in rows:
        if str(row.get("source_label") or "") != "ΕΣΗΔΗΣ":
            continue
        eshidis_id = str(row.get("eshidis_id") or row.get("display_id") or "").strip()
        deadline = str(row.get("current_deadline_at") or row.get("submission_deadline") or "").strip()
        if eshidis_id.isdigit() and deadline:
            deadlines[eshidis_id] = deadline
    return deadlines


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


INDEX_HTML = f"""<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tender Radar</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <section id="loginScreen" class="loginScreen">
    <div class="loginTop">
      <div class="brand loginBrand">
        <span class="mark">TR</span>
        <div>
          <h1>Tender Radar</h1>
          <p>Δημόσια έργα <span class="versionBadge">v{__version__}</span></p>
        </div>
      </div>
    </div>
    <div class="loginCard">
      <p class="eyebrow">Private Access</p>
      <h2>Σύνδεση Tender Radar</h2>
      <p class="loginIntro">Συνδέσου με το email και το password σου για να συνεχίσεις.</p>
      <label>Email <input id="loginEmailInput" type="email" autocomplete="email" placeholder="you@example.com"></label>
      <label>Password <input id="loginPasswordInput" type="password" autocomplete="current-password" placeholder="Password"></label>
      <button id="loginBtn" class="loginButton">Σύνδεση <span aria-hidden="true">→</span></button>
      <p id="loginStatus" class="noteText"></p>
    </div>
  </section>

  <div id="appShell" class="appShell" hidden>
  <aside class="sidebar">
    <div class="brand">
      <span class="mark">TR</span>
      <div>
        <h1>Tender Radar</h1>
        <p>Δημόσια έργα <span class="versionBadge">v{__version__}</span></p>
      </div>
    </div>
    <nav>
      <button class="nav active" data-view="overview">Αναζήτηση</button>
      <button class="nav" data-view="rules">Κανόνες</button>
      <button id="adminNavBtn" class="nav" data-view="adminPanel">Admin panel</button>
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
      <div class="topbarActions">
        <button id="refreshBtn" class="secondary">Ανανέωση</button>
        <button id="appLogoutTopBtn" class="secondary">Αποσύνδεση</button>
      </div>
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
          <button id="emailAlertsBtn" class="secondary">Email νέων έργων</button>
        </div>
      </div>

      <div class="metrics">
        <div><span id="visibleTenderCount">0</span><small>έργα στη λίστα</small></div>
        <div><span id="focusTenderCount">0</span><small>ταιριάζουν στην περιοχή</small></div>
      </div>

      <details class="sourceAudit" open>
        <summary>
          <span>Έλεγχος πηγών</span>
          <strong id="sourceAuditSummary">Δεν υπάρχει ακόμα polling state</strong>
        </summary>
        <div class="sourceAuditBody">
          <div id="sourceAuditMetrics" class="sourceAuditMetrics"></div>
          <div class="sourceAuditTableWrap">
            <table class="sourceAuditTable">
              <thead>
                <tr>
                  <th>Πηγή</th>
                  <th>Adapter</th>
                  <th>Status</th>
                  <th>Τελευταίος έλεγχος</th>
                  <th>Error</th>
                  <th>Selective</th>
                </tr>
              </thead>
              <tbody id="sourceAuditRows"></tbody>
            </table>
          </div>
        </div>
      </details>

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

    <section id="adminPanel" class="view">
      <div class="toolbar passwordSetupBox" id="passwordSetupBox" hidden>
        <label>Νέο password <input id="setupPasswordInput" type="password" autocomplete="new-password" placeholder="Τουλάχιστον 10 χαρακτήρες"></label>
        <label>Επανάληψη <input id="setupPasswordConfirmInput" type="password" autocomplete="new-password"></label>
        <button id="setupPasswordBtn">Ορισμός password</button>
        <span id="setupPasswordStatus" class="noteText">Το link ισχύει για 24 ώρες.</span>
      </div>
      <div id="adminLockedBox" class="note" hidden>Το admin panel είναι διαθέσιμο μόνο σε διαχειριστή.</div>
      <div id="adminContent" class="adminContent" hidden>
        <div class="toolbar">
          <button id="adminRefreshBtn">Ανανέωση admin audit</button>
          <button id="appLogoutBtn" class="secondary">Αποσύνδεση</button>
        </div>
        <div class="toolbar adminInviteBox">
          <label>Πρόσκληση email <input id="inviteEmailInput" type="email" placeholder="user@example.com"></label>
          <label>Ρόλος
            <select id="inviteRoleInput">
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button id="inviteUserBtn" class="secondary">Αποστολή πρόσκλησης</button>
          <span id="inviteStatus" class="noteText"></span>
        </div>
        <details class="adminUsersBox">
          <summary>Χρήστες</summary>
          <div class="tableWrap">
            <table class="adminTable">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Ρόλος</th>
                  <th>Password</th>
                  <th>Τελευταία σύνδεση</th>
                </tr>
              </thead>
              <tbody id="adminUsersRows"></tbody>
            </table>
          </div>
        </details>
        <div class="metrics adminMetrics">
          <div><span id="adminHiddenCount">0</span><small>κρυμμένα συνολικά</small></div>
          <div><span id="adminAiHiddenCount">0</span><small>AI απόρριψη</small></div>
          <div><span id="adminDismissedCount">0</span><small>Δεν με ενδιαφέρει</small></div>
          <div><span id="adminDuplicateCount">0</span><small>διπλότυπα</small></div>
          <div><span id="adminExpiredCount">0</span><small>ληγμένα</small></div>
          <div><span id="adminSourceErrorCount">0</span><small>source errors</small></div>
        </div>
        <div class="tableWrap adminTableWrap">
          <table class="adminTable">
            <thead>
              <tr>
                <th>Κατηγορία</th>
                <th>Α/Α</th>
                <th>Έργο</th>
                <th>Φορέας</th>
                <th>Αιτιολογία</th>
                <th>Ενέργεια</th>
              </tr>
            </thead>
            <tbody id="adminHiddenRows"></tbody>
          </table>
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
  </div>
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
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: Segoe UI, system-ui, -apple-system, sans-serif;
  font-size: 14px;
}
.appShell {
  display: grid;
  grid-template-columns: 248px 1fr;
  min-height: 100vh;
}
[hidden] { display: none !important; }
.loginScreen {
  min-height: 100vh;
  display: grid;
  align-content: start;
  gap: 76px;
  padding: 28px;
  background:
    linear-gradient(rgba(255,255,255,.72), rgba(255,255,255,.72)),
    linear-gradient(90deg, rgba(15,23,42,.06) 1px, transparent 1px),
    linear-gradient(rgba(15,23,42,.06) 1px, transparent 1px);
  background-size: auto, 28px 28px, 28px 28px;
}
.loginTop {
  width: min(860px, 100%);
  margin: 0 auto;
}
.loginBrand {
  width: fit-content;
  padding: 0;
  color: var(--text);
}
.loginBrand .mark {
  background: #1f2933;
  color: #f8fafc;
  border-radius: 999px;
}
.loginCard {
  width: min(560px, 100%);
  display: grid;
  gap: 20px;
  margin: 0 auto;
  padding: 34px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255,255,255,.92);
  box-shadow: 0 24px 80px rgba(15, 23, 42, .08);
}
.loginCard h2 {
  font-size: 34px;
}
.loginIntro {
  max-width: 420px;
  color: var(--muted);
  font-size: 17px;
  line-height: 1.6;
}
.loginCard input {
  min-width: 0;
  width: 100%;
  min-height: 50px;
}
.loginButton {
  min-height: 66px;
  justify-content: space-between;
  padding: 0 26px;
  border-radius: 12px;
  background: #0f766e;
  font-size: 18px;
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
.versionBadge {
  display: inline-flex;
  align-items: center;
  margin-left: 8px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid #4c6174;
  color: #cfe8e1;
  font-size: 12px;
  font-weight: 800;
}
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
.topbarActions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: end;
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
.adminMetrics {
  grid-template-columns: repeat(3, minmax(120px, 1fr));
}
.adminTableWrap {
  margin-top: 14px;
}
.adminTable {
  min-width: 1120px;
  table-layout: fixed;
}
.adminTable td:nth-child(3),
.adminTable td:nth-child(4),
.adminTable td:nth-child(5) {
  white-space: normal;
}
.sourceAudit {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin-bottom: 14px;
  overflow: hidden;
}
.sourceAudit summary {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
  color: var(--muted);
  font-weight: 800;
}
.sourceAudit summary strong {
  color: var(--text);
  font-size: 12px;
  text-align: right;
}
.sourceAuditBody {
  border-top: 1px solid var(--line);
  padding: 12px 14px 14px;
}
.sourceAuditMetrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.sourceAuditMetric {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 9px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #334155;
  font-size: 12px;
  font-weight: 800;
}
.sourceAuditTableWrap {
  overflow: auto;
}
.sourceAuditTable {
  min-width: 880px;
  table-layout: fixed;
}
.sourceAuditTable td {
  font-size: 12px;
}
.sourceAuditSource {
  font-weight: 800;
}
.sourceAuditUrl {
  display: block;
  margin-top: 3px;
  color: var(--muted);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.statusChip {
  display: inline-grid;
  place-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #334155;
  font-size: 11px;
  font-weight: 900;
}
.statusChip.changed {
  background: #dcfce7;
  color: #166534;
}
.statusChip.unchanged {
  background: #e0f2fe;
  color: #075985;
}
.statusChip.error {
  background: #fee2e2;
  color: #991b1b;
}
.statusChip.waiting {
  background: #fef3c7;
  color: #92400e;
}
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
  .appShell { grid-template-columns: 1fr; }
  .sidebar { position: static; }
  nav { grid-template-columns: repeat(4, 1fr); }
  main { padding: 14px; }
  .searchBand,
  .workspace {
    grid-template-columns: 1fr;
  }
  .metrics,
  .adminMetrics { grid-template-columns: 1fr; }
  .rulesGrid,
  .editorGrid {
    grid-template-columns: 1fr;
  }
  .editorGrid .wide {
    grid-column: auto;
  }
  .loginScreen {
    gap: 54px;
    padding: 22px;
  }
  .loginCard {
    padding: 28px 24px;
    border-radius: 16px;
  }
  .loginCard h2 {
    font-size: 29px;
  }
  .workspace {
    display: block;
  }
  .tableWrap {
    overflow: visible;
    border: 0;
    background: transparent;
  }
  table,
  .tenderTable,
  .adminTable,
  .sourceAuditTable {
    min-width: 0;
  }
  .tenderTable thead {
    display: none;
  }
  .tenderTable,
  .tenderTable tbody,
  .tenderTable tr,
  .tenderTable td {
    display: block;
    width: 100%;
  }
  .tenderTable tr {
    margin-bottom: 12px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--panel);
    overflow: hidden;
  }
  .tenderTable td {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr);
    gap: 12px;
    padding: 10px 12px;
    border-bottom: 1px solid #eef2f6;
    white-space: normal;
  }
  .tenderTable td::before {
    content: attr(data-label);
    color: var(--muted);
    font-size: 11px;
    font-weight: 900;
    text-transform: uppercase;
  }
  .tenderTitle,
  .authorityCell {
    max-width: none;
  }
  .deadlineCell,
  .budgetCell {
    white-space: normal;
  }
  .previewPane {
    position: static;
    margin-top: 14px;
  }
}
"""


APP_JS = """
const state = {
  selected: null,
  dashboard: null,
  sourcePolling: null,
  profiles: [],
  evaluationProfiles: [],
  documentTypes: [],
  ruleProfilePath: null,
  evaluationConfig: null,
  selectedRuleId: null,
  adminAudit: null,
  session: null,
};
const $ = (id) => document.getElementById(id);

document.querySelectorAll('.nav').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
    button.classList.add('active');
    $(button.dataset.view).classList.add('active');
    if (button.dataset.view === 'adminPanel') {
      loadAdminAudit().catch(() => {});
    }
  });
});

const setupToken = new URLSearchParams(window.location.search).get('token');
if (window.location.pathname === '/password-setup' && setupToken) {
  $('loginScreen').hidden = true;
  $('appShell').hidden = false;
  document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
  document.querySelector('[data-view="adminPanel"]').classList.add('active');
  $('adminPanel').classList.add('active');
  $('passwordSetupBox').hidden = false;
}

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
  if (!state.session && window.location.pathname !== '/password-setup') return;
  const status = await api('/api/status');
  state.profiles = status.profiles || [];
  state.evaluationProfiles = status.evaluation_profiles || [];
  state.documentTypes = status.document_types || [];
  fillSelect('profileSelect', state.profiles);
  fillSelect('evaluationProfileSelect', state.evaluationProfiles);
  fillSelect('ruleProfileSelect', state.evaluationProfiles);
  await loadDashboard();
  await loadSourcePolling();
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

async function loadSourcePolling() {
  const payload = await api('/api/source-polling');
  state.sourcePolling = payload;
  renderSourcePolling(payload);
}

async function refreshRuntimeViews() {
  await loadDashboard();
  await loadSourcePolling();
  if (!$('adminContent').hidden) {
    await loadAdminAudit();
  }
}

async function adminApi(path, options = {}) {
  return api(path, options);
}

async function adminLogin() {
  const email = $('loginEmailInput').value;
  const password = $('loginPasswordInput').value;
  $('loginStatus').textContent = 'Έλεγχος σύνδεσης...';
  try {
    const payload = await adminApi('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    $('loginPasswordInput').value = '';
    applySession(payload.session || null);
    $('loginStatus').textContent = 'Συνδέθηκε.';
    await refresh();
  } catch (error) {
    $('loginStatus').textContent = String(error.message || error);
  }
}

async function setupPassword() {
  const password = $('setupPasswordInput').value;
  const confirm = $('setupPasswordConfirmInput').value;
  if (password !== confirm) {
    $('setupPasswordStatus').textContent = 'Τα password δεν ταιριάζουν.';
    return;
  }
  $('setupPasswordStatus').textContent = 'Αποθήκευση password...';
  try {
    await adminApi('/api/admin/set-password', { method: 'POST', body: JSON.stringify({ token: setupToken, password }) });
    $('setupPasswordInput').value = '';
    $('setupPasswordConfirmInput').value = '';
    $('setupPasswordStatus').textContent = 'Το password ορίστηκε.';
    window.history.replaceState({}, document.title, '/');
    const auth = await api('/api/auth/status');
    applySession(auth.session || null);
    await refresh();
  } catch (error) {
    $('setupPasswordStatus').textContent = String(error.message || error);
  }
}

async function inviteUser() {
  const email = $('inviteEmailInput').value;
  const role = $('inviteRoleInput').value;
  $('inviteStatus').textContent = 'Στέλνω πρόσκληση...';
  try {
    await adminApi('/api/admin/invite-user', { method: 'POST', body: JSON.stringify({ email, role }) });
    $('inviteEmailInput').value = '';
    $('inviteStatus').textContent = 'Η πρόσκληση στάλθηκε.';
    await loadAdminUsers();
  } catch (error) {
    $('inviteStatus').textContent = String(error.message || error);
  }
}

async function loadAdminUsers() {
  const payload = await adminApi('/api/admin/users');
  const tbody = $('adminUsersRows');
  tbody.innerHTML = '';
  const users = payload.users || [];
  if (!users.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="emptyState">Δεν υπάρχουν χρήστες.</td></tr>';
    return;
  }
  for (const user of users) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(user.email || '')}</td>
      <td><span class="statusChip unchanged">${escapeHtml(user.role || '')}</span></td>
      <td>${user.password_set ? 'Ορισμένο' : 'Σε πρόσκληση'}</td>
      <td>${escapeHtml(user.last_login_at || '')}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function adminLogout() {
  await adminApi('/api/auth/logout', { method: 'POST', body: JSON.stringify({}) });
  state.adminAudit = null;
  state.session = null;
  $('appShell').hidden = true;
  $('loginScreen').hidden = false;
  $('adminContent').hidden = true;
  $('adminLockedBox').hidden = true;
  $('loginStatus').textContent = 'Αποσυνδέθηκε.';
}

async function loadAdminAudit() {
  if (!state.session || state.session.role !== 'admin') {
    $('adminContent').hidden = true;
    $('adminLockedBox').hidden = false;
    return;
  }
  try {
    const payload = await adminApi('/api/admin/audit');
    state.adminAudit = payload;
    $('adminLockedBox').hidden = true;
    $('adminContent').hidden = false;
    renderAdminAudit(payload);
    await loadAdminUsers();
  } catch (error) {
    $('adminContent').hidden = true;
    $('adminLockedBox').hidden = false;
  }
}

async function loadAuthStatus() {
  const auth = await api('/api/auth/status');
  applySession(auth.session || null);
  if (state.session) {
    await refresh();
  }
}

function applySession(session) {
  state.session = session;
  const isLoggedIn = Boolean(session);
  $('loginScreen').hidden = isLoggedIn;
  $('appShell').hidden = !isLoggedIn;
  $('adminNavBtn').hidden = !session || session.role !== 'admin';
  if (isLoggedIn && session.role !== 'admin' && $('adminPanel').classList.contains('active')) {
    document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
    document.querySelector('[data-view="overview"]').classList.add('active');
    $('overview').classList.add('active');
  }
}

function renderAdminAudit(payload) {
  const summary = payload.summary || {};
  $('adminHiddenCount').textContent = summary.hidden_total || 0;
  $('adminAiHiddenCount').textContent = summary.ai_hidden || 0;
  $('adminDismissedCount').textContent = summary.dismissed || 0;
  $('adminDuplicateCount').textContent = summary.duplicates || 0;
  $('adminExpiredCount').textContent = summary.expired || 0;
  $('adminSourceErrorCount').textContent = summary.source_errors || 0;
  const tbody = $('adminHiddenRows');
  const rows = payload.hidden_rows || [];
  tbody.innerHTML = '';
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="emptyState">Δεν υπάρχουν κρυμμένα έργα στο τρέχον audit.</td></tr>';
    return;
  }
  for (const row of rows) {
    const tr = document.createElement('tr');
    const sourceLink = row.official_url
      ? `<a class="button secondary tinyButton" href="${escapeHtml(row.official_url)}" target="_blank" rel="noreferrer">Open</a>`
      : '';
    const restoreButton = row.restorable
      ? `<button class="tinyButton restoreHiddenRow" data-key="${escapeHtml(row.row_key)}">Επαναφορά</button>`
      : '<span class="noteText">Audit only</span>';
    tr.innerHTML = `
      <td><span class="statusChip ${adminCategoryClass(row.category)}">${escapeHtml(adminCategoryLabel(row.category))}</span></td>
      <td><strong>${escapeHtml(row.display_id || '')}</strong><br><span class="noteText">${escapeHtml(row.source_label || '')}</span></td>
      <td class="tenderTitle">${escapeHtml(row.title || '')}${row.ai_decision ? `<span class="pill">${escapeHtml(row.ai_decision)}</span>` : ''}</td>
      <td class="authorityCell">${escapeHtml(row.authority_name || '')}</td>
      <td>${escapeHtml(row.reason || '')}${row.ai_confidence ? `<br><span class="noteText">confidence ${escapeHtml(row.ai_confidence)}</span>` : ''}</td>
      <td><div class="actionStack">${sourceLink}${restoreButton}</div></td>
    `;
    tbody.appendChild(tr);
  }
  document.querySelectorAll('.restoreHiddenRow').forEach((button) => {
    button.addEventListener('click', () => restoreHiddenRow(button.dataset.key));
  });
}

function adminCategoryLabel(category) {
  return {
    AI_HIDDEN: 'AI',
    DISMISSED: 'Δεν με ενδιαφέρει',
    DUPLICATE: 'Διπλότυπο',
    EXPIRED: 'Ληγμένο',
  }[category] || category || 'Άγνωστο';
}

function adminCategoryClass(category) {
  if (category === 'AI_HIDDEN') return 'waiting';
  if (category === 'DISMISSED') return 'error';
  if (category === 'DUPLICATE') return 'unchanged';
  if (category === 'EXPIRED') return 'changed';
  return 'waiting';
}

async function restoreHiddenRow(rowKey) {
  if (!rowKey) return;
  const reason = window.prompt('Γιατί επαναφέρεις αυτό το έργο; Αυτό θα χρησιμοποιηθεί ως feedback για τους επόμενους κανόνες.', '');
  if (reason === null) return;
  await adminApi('/api/admin/restore', { method: 'POST', body: JSON.stringify({ row_key: rowKey, reason }) });
  await refreshRuntimeViews();
  await loadAdminAudit();
}

function renderSourcePolling(payload) {
  const summary = payload.summary || {};
  const rows = payload.rows || [];
  $('sourceAuditSummary').textContent = rows.length
    ? `${summary.configured_total || 0} πηγές · ${summary.unchanged_total || 0} skip · ${summary.selective_changed_total || 0} selective αλλαγές · ${summary.selective_error_total || 0} selective errors`
    : 'Δεν υπάρχει ακόμα polling state';
  $('sourceAuditMetrics').innerHTML = [
    ['Configured', summary.configured_total || 0],
    ['Tracked', summary.tracked_total || 0],
    ['Selective', summary.selective_capable_total || 0],
    ['Changed', summary.changed_total || 0],
    ['Selective changed', summary.selective_changed_total || 0],
    ['Skip', summary.unchanged_total || 0],
    ['Errors', summary.error_total || 0],
    ['Selective errors', summary.selective_error_total || 0],
    ['Templates', summary.requires_identifier_total || 0],
    ['Never checked', summary.never_checked_total || 0],
  ].map(([label, value]) => `<span class="sourceAuditMetric">${escapeHtml(label)} ${escapeHtml(value)}</span>`).join('');
  const tbody = $('sourceAuditRows');
  tbody.innerHTML = '';
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="emptyState">Δεν έχει τρέξει ακόμα source polling σε αυτό το runtime.</td></tr>';
    return;
  }
  for (const source of rows) {
    const statusClass = sourceStatusClass(source.last_status, source.last_error);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <span class="sourceAuditSource">${escapeHtml(source.name || source.source_id)}</span>
        <span class="sourceAuditUrl">${escapeHtml(source.source_id || '')}${source.source_url ? ` · ${escapeHtml(source.source_url)}` : ''}</span>
      </td>
      <td>${escapeHtml(source.family_or_adapter || '')}</td>
      <td><span class="statusChip ${statusClass}">${escapeHtml(source.last_status || 'UNKNOWN')}</span></td>
      <td>${escapeHtml(formatDateTime(source.last_checked_at))}</td>
      <td>${escapeHtml(source.last_error || '')}</td>
      <td>${source.selective_refresh_capable ? 'Ναι' : 'Όχι'}</td>
    `;
    tbody.appendChild(tr);
  }
}

function sourceStatusClass(status, error) {
  if (error || status === 'ERROR') return 'error';
  if (status === 'CHANGED') return 'changed';
  if (status === 'SKIPPED_UNCHANGED') return 'unchanged';
  return 'waiting';
}

function formatDateTime(value) {
  if (!value) return '';
  return String(value).replace('T', ' ').replace('+00:00', ' UTC');
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
    const officialStatusText = tender.official_status_label
      ? `<span class="pill">${escapeHtml(tender.official_status_label)}</span>`
      : '';
    const aiText = tender.ai_triage?.decision
      ? `<span class="pill">${escapeHtml(tender.ai_triage.decision)}</span>`
      : '';
    const zipUrl = `/api/document-zip?identifier=${encodeURIComponent(fetchIdentifier)}`;
    const tr = document.createElement('tr');
    tr.dataset.key = rowKey;
    if (state.selected === rowKey) tr.classList.add('selectedRow');
    tr.innerHTML = `
      <td data-label="Α/Α"><strong>${escapeHtml(tender.display_id || tender.eshidis_id || '')}</strong></td>
      <td data-label="Πηγή">${escapeHtml(tender.source_label || '')}</td>
      <td data-label="Έργο" class="tenderTitle">${escapeHtml(tender.title || '')}${tender.interest_reason ? `<span class="pill">${escapeHtml(tender.interest_reason)}</span>` : ''}${officialStatusText}${linkedText}${aiText}</td>
      <td data-label="Φορέας" class="authorityCell">${escapeHtml(tender.authority_name || '')}</td>
      <td data-label="Προϋπολογισμός" class="budgetCell">${escapeHtml(tender.budget_display || '')}</td>
      <td data-label="Λήξη" class="deadlineCell">${escapeHtml(tender.deadline_display || '')}</td>
      <td data-label="Ενέργειες">
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
    await refreshRuntimeViews();
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
  await refreshRuntimeViews();
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
  await refreshRuntimeViews();
}

async function renderAuthorityPreview(rowKey) {
  const payload = await api(`/api/authority-document-preview?row_key=${encodeURIComponent(rowKey)}`);
  const docs = payload.documents || [];
  const linkedIds = payload.linked_eshidis_ids || [];
  const linkedFileCount = Number(payload.linked_eshidis_file_count || 0);
  if (!docs.length) {
    $('previewBody').innerHTML = '<div class="emptyState">Υπάρχουν links εγγράφων στη σελίδα του φορέα. Πάτα Fetch για να κατέβουν τοπικά και μετά ZIP.</div>';
    return;
  }
  const linkedBlock = linkedIds.length
    ? `<div class="docItem linkedBox"><h4>Σύνδεση με ΕΣΗΔΗΣ</h4><p>Βρέθηκε Α/Α ΕΣΗΔΗΣ ${escapeHtml(linkedIds.join(', '))}. ${linkedFileCount ? `Υπάρχουν ήδη ${linkedFileCount} επίσημα αρχεία ΕΣΗΔΗΣ διαθέσιμα για zip.` : 'Το Fetch αυτής της γραμμής θα επιχειρήσει να κατεβάσει και τον επίσημο φάκελο ΕΣΗΔΗΣ.'}</p></div>`
    : `<div class="docItem"><h4>Δεν βρέθηκε ακόμα ΕΣΗΔΗΣ</h4><p>Κρατάμε τη δημοσίευση του φορέα ως υποψήφια. Τα κατεβασμένα έντυπα ελέγχθηκαν για άρθρο 2.2, links και Α/Α ΕΣΗΔΗΣ.</p></div>`;
  $('previewBody').innerHTML = linkedBlock + docs.map((doc) => `
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
    await refreshRuntimeViews();
    if (path === '/api/discover' && !body?.backfill && finalResult.ok !== false) {
      startAiTriageThenEnrichment().catch((error) => {
        $('statusText').textContent = `Σφάλμα AI ελέγχου: ${error}`;
      });
    }
  } catch (error) {
    $('commandOutput').textContent = String(error);
    $('statusText').textContent = 'Σφάλμα';
  } finally {
    setBusy(false, $('statusText').textContent);
  }
}

async function startAiTriageThenEnrichment() {
  const scope = $('allGreeceToggle').checked ? 'all' : 'focus';
  const sort = $('sortSelect').value || 'deadline_asc';
  const initial = await api('/api/ai-triage', {
    method: 'POST',
    body: JSON.stringify({ scope, sort, batch_size: 20 }),
  });
  if (!initial.job_id) return;
  $('statusText').textContent = 'AI έλεγχος έργων σε εξέλιξη';
  const aiJob = await pollJob(initial.job_id, 'AI διαλογή έργων με OpenAI');
  $('commandOutput').textContent = JSON.stringify(aiJob, null, 2);
  await refreshRuntimeViews();
  const aiResult = aiJob.result || {};
  if (aiJob.status === 'failed' || aiResult.ok === false) {
    $('statusText').textContent = 'AI έλεγχος απέτυχε · συνεχίζω με deterministic enrichment';
  }
  await startCandidateEnrichment();
}

async function startCandidateEnrichment() {
  const scope = $('allGreeceToggle').checked ? 'all' : 'focus';
  const initial = await api('/api/enrich-candidates', {
    method: 'POST',
    body: JSON.stringify({ scope, limit: 50 }),
  });
  if (!initial.job_id) return;
  $('statusText').textContent = 'Αυτόματος έλεγχος μη-ΕΣΗΔΗΣ έργων σε εξέλιξη';
  const job = await pollJob(initial.job_id, 'Αυτόματος εντοπισμός Α/Α ΕΣΗΔΗΣ');
  $('commandOutput').textContent = JSON.stringify(job, null, 2);
  const result = job.result || {};
  const summary = result.summary || {};
  $('statusText').textContent = `Έλεγχος ΕΣΗΔΗΣ: ${summary.enriched_with_eshidis || 0} συνδέθηκαν, ${summary.failed || 0} απέτυχαν`;
  await refreshRuntimeViews();
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

$('loginBtn').addEventListener('click', () => adminLogin().catch((error) => { $('loginStatus').textContent = String(error); }));
$('loginPasswordInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') adminLogin().catch((error) => { $('loginStatus').textContent = String(error); });
});
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
$('emailAlertsBtn').addEventListener('click', () => {
  const scope = $('allGreeceToggle').checked ? 'all' : 'focus';
  const sort = $('sortSelect').value || 'deadline_asc';
  runAction('/api/email-alerts', { scope, sort, dry_run: false }, 'Αποστολή email για νέα έργα...');
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
$('setupPasswordBtn').addEventListener('click', () => setupPassword().catch((error) => { $('setupPasswordStatus').textContent = String(error); }));
$('inviteUserBtn').addEventListener('click', () => inviteUser().catch((error) => { $('inviteStatus').textContent = String(error); }));
$('adminRefreshBtn').addEventListener('click', () => loadAdminAudit().catch(() => {}));
$('appLogoutBtn').addEventListener('click', () => adminLogout().catch((error) => { $('loginStatus').textContent = String(error); }));
$('appLogoutTopBtn').addEventListener('click', () => adminLogout().catch((error) => { $('loginStatus').textContent = String(error); }));

if (window.location.pathname !== '/password-setup') {
  loadAuthStatus().catch((error) => { $('loginStatus').textContent = String(error); });
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
