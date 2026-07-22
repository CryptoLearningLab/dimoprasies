from __future__ import annotations

import argparse
import base64
from copy import deepcopy
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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tender_radar import __version__
from tender_radar.config import load_config
from tender_radar.db import (
    admin_hidden_events_by_key,
    count_enabled_admin_users,
    create_admin_session,
    create_admin_invite,
    delete_admin_session,
    delete_stale_verified_tender_links,
    dismiss_tender as dismiss_tender_in_db,
    dismiss_user_tender,
    get_admin_invite,
    get_admin_session,
    get_admin_user,
    get_admin_user_by_id,
    get_source_document,
    get_source_state,
    ignored_user_tender_keys,
    ignored_tender_keys as ignored_tender_keys_from_db,
    list_admin_users,
    list_searchable_documents,
    list_source_documents,
    list_tender_dismissals,
    list_user_tender_dismissals,
    list_source_states,
    list_verified_tender_links,
    mark_admin_invite_used,
    notification_already_sent,
    notification_logs_by_row_key,
    record_admin_user_login,
    record_source_run,
    record_notification_sent,
    remove_tender_dismissal,
    remove_user_tender_dismissal,
    triage_overrides_by_key as db_triage_overrides_by_key,
    user_triage_overrides_by_key as db_user_triage_overrides_by_key,
    upsert_admin_hidden_event,
    upsert_admin_user,
    upsert_triage_override,
    upsert_user_interest_profile,
    upsert_user_triage_override,
    upsert_source_document,
    upsert_source_state,
    upsert_verified_tender_link,
    user_interest_profile as db_user_interest_profile,
)
from tender_radar.discovery_watermark import (
    append_discovery_run,
    build_discovery_run_record,
    latest_discovery_run,
    latest_successful_discovery_run,
    utc_now_iso,
)
from tender_radar.documents import analyze_document
from tender_radar.entalmata import archived_entalmata_count, entalma_file_path, list_entalmata, scan_entalmata
from tender_radar.evaluation import normalize_evaluation_config, save_evaluation_config
from tender_radar.ai_triage import AI_TRIAGE_PROMPT_VERSION
from tender_radar.pricing import ingest_pricing_active_eshidis, search_pricing_rows
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
ADMIN_USER_ROLES = ("admin", "pricing", "tester", "user")
PASSWORD_SETUP_TOKEN_TTL_MINUTES = 60
MAX_BACKFILL_ESHIDIS_LIMIT = 500
MAX_BACKFILL_KIMDIS_PAGES = 80
MAX_REVERSE_SEARCH_RESULTS = 80
MAX_REVERSE_DOCUMENT_MATCHES_PER_ROW = 6
MAX_REVERSE_TEXT_READ_CHARS = 220_000
COMMAND_LOCK = threading.Lock()
ENRICHMENT_LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}
ADMIN_SESSIONS_LOCK = threading.Lock()
ADMIN_SESSIONS: dict[str, dict[str, str]] = {}
ADMIN_LOGIN_CODES_LOCK = threading.Lock()
ADMIN_LOGIN_CODES: dict[str, dict[str, Any]] = {}
PAYLOAD_CACHE_LOCK = threading.Lock()
PAYLOAD_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
PAYLOAD_CACHE_TTL_SECONDS = 90
DATA_CACHE_LOCK = threading.Lock()
DATA_CACHE: dict[tuple[Any, ...], Any] = {}


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
            session = self._admin_session() or {}
            self._send_json(cached_dashboard_payload(scope=scope, sort=sort, user_email=session.get("email")))
            return
        if parsed.path == "/api/source-polling":
            self._send_json(source_polling_payload())
            return
        if parsed.path == "/api/user/interest-profile":
            session = self._admin_session()
            if not session or not session.get("email"):
                self._send_json({"ok": False, "error": "Login required."}, status=401)
                return
            self._send_json(user_interest_profile_payload(str(session["email"])))
            return
        if parsed.path == "/api/entalmata":
            self._send_json(entalmata_payload())
            return
        if parsed.path == "/api/pricing/ingest-status":
            session = self._admin_session()
            if not session or session.get("role") not in {"admin", "pricing"}:
                self._send_json({"ok": False, "error": "Pricing access required."}, status=403)
                return
            self._send_json(pricing_ingest_status_payload())
            return
        if parsed.path == "/api/admin/audit":
            session = self._admin_session()
            if not session or session.get("role") != "admin":
                self._send_json({"ok": False, "authenticated": False, **admin_status_payload()}, status=401)
                return
            query = parse_qs(parsed.query)
            include = query.get("include", ["summary"])[0]
            self._send_json(cached_admin_audit_payload(user_email=session.get("email"), include=include))
            return
        if parsed.path == "/api/admin/users":
            session = self._admin_session()
            if not session or session.get("role") != "admin":
                self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                return
            self._send_json(admin_users_payload())
            return
        if parsed.path == "/api/admin/secrets":
            session = self._admin_session()
            if not session or session.get("role") != "admin":
                self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                return
            self._send_json(admin_secrets_payload())
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
        if parsed.path == "/api/entalmata-file":
            query = parse_qs(parsed.query)
            ada = str(query.get("ada", [""])[0]).strip()
            path = entalma_file_path(runtime_db_path(), ada)
            if not path:
                self._send_json({"error": "Entalma PDF file is not available."}, status=404)
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
            if parsed.path == "/api/auth/request-password-reset":
                self._send_json(request_password_reset(payload, base_url=self._public_base_url()))
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
                session = self._admin_session() or {}
                scope = str(payload.get("scope") or "focus")
                sort = str(payload.get("sort") or "deadline_asc")
                dry_run = bool(payload.get("dry_run", False))
                recipient = str(payload.get("recipient") or "").strip() or None
                self._send_json(
                    start_job(
                        "email-alerts",
                        run_email_alerts,
                        scope=scope,
                        sort=sort,
                        recipient=recipient,
                        dry_run=dry_run,
                        user_email=session.get("email"),
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/reverse-search":
                session = self._admin_session() or {}
                self._send_json(reverse_search_payload(payload, user_email=session.get("email")))
                return
            if parsed.path == "/api/pricing/search":
                session = self._admin_session()
                if not session or session.get("role") not in {"admin", "pricing"}:
                    self._send_json({"ok": False, "error": "Pricing access required."}, status=403)
                    return
                self._send_json(pricing_search_payload(payload))
                return
            if parsed.path == "/api/pricing/ingest-active":
                session = self._admin_session()
                if not session or session.get("role") not in {"admin", "pricing"}:
                    self._send_json({"ok": False, "error": "Pricing access required."}, status=403)
                    return
                discovery_limit = int(payload.get("discovery_limit") or 500)
                attachment_limit = int(payload.get("attachment_limit") or 50)
                project_limit_raw = payload.get("project_limit")
                project_limit = int(project_limit_raw) if project_limit_raw not in (None, "", 0, "0") else None
                max_new_raw = payload.get("max_new_projects")
                max_new_projects = int(max_new_raw) if max_new_raw not in (None, "", 0, "0") else None
                self._send_json(
                    start_job(
                        "pricing-ingest-active",
                        run_pricing_active_ingest,
                        discovery_limit=discovery_limit,
                        attachment_limit=attachment_limit,
                        project_limit=project_limit,
                        max_new_projects=max_new_projects,
                    ),
                    status=202,
                )
                return
            if parsed.path == "/api/entalmata/scan":
                self._send_json(start_job("entalmata-scan", run_entalmata_scan), status=202)
                return
            if parsed.path == "/api/dismiss-tender":
                row_key = require_row_key(payload)
                session = self._admin_session()
                if not session or not session.get("email"):
                    self._send_json({"ok": False, "error": "Login required."}, status=401)
                    return
                self._send_json(dismiss_tender(row_key, user_email=session["email"]))
                return
            if parsed.path == "/api/user/interest-profile":
                session = self._admin_session()
                if not session or not session.get("email"):
                    self._send_json({"ok": False, "error": "Login required."}, status=401)
                    return
                self._send_json(update_user_interest_profile(str(session["email"]), payload))
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
            if parsed.path == "/api/admin/update-user-role":
                session = self._admin_session()
                if not session or session.get("role") != "admin":
                    self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                    return
                self._send_json(update_admin_user_role(payload, actor_email=session.get("email")))
                return
            if parsed.path == "/api/admin/secrets":
                session = self._admin_session()
                if not session or session.get("role") != "admin":
                    self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                    return
                self._send_json(update_admin_secrets(payload, actor_email=session.get("email")))
                return
            if parsed.path == "/api/admin/logout":
                self._admin_logout()
                return
            if parsed.path == "/api/admin/restore":
                session = self._admin_session()
                if not session or session.get("role") != "admin":
                    self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                    return
                row_key = require_row_key(payload)
                reason = str(payload.get("reason") or "").strip() or None
                self._send_json(restore_admin_row(row_key=row_key, reason=reason, user_email=session.get("email")))
                return
            if parsed.path == "/api/admin/review-feedback":
                session = self._admin_session()
                if not session or session.get("role") != "admin":
                    self._send_json({"ok": False, "error": "Admin login required."}, status=401)
                    return
                row_key = require_row_key(payload)
                action = require_admin_review_feedback_action(payload)
                reason = str(payload.get("reason") or "").strip() or None
                self._send_json(
                    admin_review_feedback(
                        row_key=row_key,
                        action=action,
                        reason=reason,
                        actor_email=session.get("email"),
                        user_email=session.get("email"),
                    )
                )
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
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=43200)).isoformat()
        token_hash = hash_reset_token(token)
        create_admin_session(
            runtime_db_path(),
            token_hash=token_hash,
            email=email,
            role=role,
            expires_at=expires_at,
        )
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
            delete_admin_session(runtime_db_path(), hash_reset_token(token))
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
            session = ADMIN_SESSIONS.get(token)
        if session:
            return session
        persisted = get_admin_session(runtime_db_path(), hash_reset_token(token))
        if not persisted:
            return None
        session = {"email": persisted.email, "role": persisted.role}
        with ADMIN_SESSIONS_LOCK:
            ADMIN_SESSIONS[token] = session
        return session

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


def run_entalmata_scan() -> dict[str, Any]:
    if not COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another command is already running. Wait for it to finish."}
    try:
        report = scan_entalmata(
            db_path=runtime_db_path(),
            config_path=REPO_ROOT / "config/diavgeia_entalmata.yml",
            download_dir=REPO_ROOT / "work/download_audit/diavgeia_entalmata",
        )
        report_path = REPO_ROOT / "work/reports/diavgeia_entalmata_latest.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        report["entalmata"] = entalmata_payload()
        return report
    finally:
        COMMAND_LOCK.release()


def run_pricing_active_ingest(
    *,
    discovery_limit: int = 500,
    attachment_limit: int = 50,
    project_limit: int | None = None,
    max_new_projects: int | None = None,
) -> dict[str, Any]:
    if not COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another command is already running. Wait for it to finish."}
    try:
        report_path = REPO_ROOT / "work/reports/pricing_active_candidates.json"
        output_path = REPO_ROOT / "work/reports/pricing_active_ingest_latest.json"
        payload = ingest_pricing_active_eshidis(
            runtime_db_path(),
            work_dir=REPO_ROOT / "work/pricing",
            discovery_limit=discovery_limit,
            attachment_limit=attachment_limit,
            project_limit=project_limit,
            max_new_projects=max_new_projects,
            allow_insecure_tls=True,
            keep_heavy_files=False,
            report_path=report_path,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**payload, "report_path": str(output_path)}
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
    invalidate_ui_payload_cache()
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


def cached_payload(key: tuple[Any, ...], builder: Any, *, ttl_seconds: int = PAYLOAD_CACHE_TTL_SECONDS) -> dict[str, Any]:
    now = time.time()
    with PAYLOAD_CACHE_LOCK:
        cached = PAYLOAD_CACHE.get(key)
        if cached and now - float(cached.get("created_at") or 0) <= ttl_seconds:
            payload = deepcopy(cached.get("payload") or {})
            payload["cache"] = {"hit": True, "age_seconds": round(now - float(cached.get("created_at") or now), 3)}
            return payload
    started = time.perf_counter()
    payload = builder()
    elapsed = time.perf_counter() - started
    if isinstance(payload, dict):
        payload = {**payload, "cache": {"hit": False, "age_seconds": 0.0, "generated_seconds": round(elapsed, 3)}}
    with PAYLOAD_CACHE_LOCK:
        PAYLOAD_CACHE[key] = {"created_at": now, "payload": deepcopy(payload)}
    if elapsed >= 1.0:
        print(f"[ui-perf] cache_miss key={key!r} seconds={elapsed:.3f}", flush=True)
    return deepcopy(payload)


def invalidate_ui_payload_cache() -> None:
    with PAYLOAD_CACHE_LOCK:
        PAYLOAD_CACHE.clear()
    with DATA_CACHE_LOCK:
        DATA_CACHE.clear()


def path_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def cached_data(key: tuple[Any, ...], builder: Any) -> Any:
    with DATA_CACHE_LOCK:
        if key in DATA_CACHE:
            return deepcopy(DATA_CACHE[key])
    value = builder()
    with DATA_CACHE_LOCK:
        DATA_CACHE[key] = deepcopy(value)
    return deepcopy(value)


def cached_dashboard_payload(*, scope: str, sort: str, user_email: str | None = None) -> dict[str, Any]:
    safe_scope = dashboard_scope(scope)
    safe_sort = sort if sort in {"deadline_asc", "budget_desc"} else "deadline_asc"
    key = ("dashboard", safe_scope, safe_sort, user_email or "")
    return cached_payload(
        key,
        lambda: dashboard_payload(
            scope=safe_scope,
            sort=safe_sort,
            user_email=user_email,
            perform_expired_cleanup=False,
        ),
    )


def cached_admin_audit_payload(*, user_email: str | None = None, include: str = "summary") -> dict[str, Any]:
    safe_include = include if include in {"summary", "review", "hidden", "all"} else "summary"
    return cached_payload(
        ("admin_audit", (user_email or "").strip().lower(), safe_include),
        lambda: admin_audit_payload(
            user_email=user_email,
            include_hidden_rows=safe_include in {"hidden", "all"},
            include_review_queue=safe_include in {"review", "all"},
        ),
    )


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
    safe_scope = dashboard_scope(scope)
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
    enriched_rows = rows_with_document_evidence(rows)
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


def rows_with_document_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_evidence_by_key = source_document_evidence_by_row_key() or {}
    kimdis_documents = kimdis_documents_by_official_id()
    authority_documents = authority_documents_by_key()
    return [
        row_with_document_evidence(
            row,
            source_evidence_by_key=source_evidence_by_key,
            kimdis_documents=kimdis_documents,
            authority_documents=authority_documents,
        )
        for row in rows
    ]


def row_with_document_evidence(
    row: dict[str, Any],
    *,
    source_evidence_by_key: dict[str, list[dict[str, Any]]] | None = None,
    kimdis_documents: dict[str, dict[str, Any]] | None = None,
    authority_documents: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("official_id") or row.get("display_id") or "").strip()
    if not row_key:
        return row
    documents = document_evidence_for_row(
        row,
        row_key=row_key,
        source_evidence_by_key=source_evidence_by_key,
        kimdis_documents=kimdis_documents,
        authority_documents=authority_documents,
    )
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


def document_evidence_for_row(
    row: dict[str, Any],
    *,
    row_key: str,
    source_evidence_by_key: dict[str, list[dict[str, Any]]] | None = None,
    kimdis_documents: dict[str, dict[str, Any]] | None = None,
    authority_documents: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    evidence_by_url: dict[str, dict[str, Any]] = {}
    source_documents = (
        source_evidence_by_key.get(row_key, [])
        if source_evidence_by_key is not None
        else sqlite_source_document_evidence(row_key)
    )
    for document in source_documents:
        evidence_by_url[str(document.get("document_url") or document.get("name") or len(evidence_by_url))] = document
    for document in legacy_row_document_evidence(
        row,
        row_key=row_key,
        kimdis_documents=kimdis_documents,
        authority_documents=authority_documents,
    ):
        evidence_by_url.setdefault(str(document.get("document_url") or document.get("name") or len(evidence_by_url)), document)
    evidence = list(evidence_by_url.values())
    evidence.sort(key=lambda item: document_evidence_rank(item))
    return evidence[:4]


def sqlite_source_document_evidence(row_key: str) -> list[dict[str, Any]]:
    grouped = source_document_evidence_by_row_key()
    if grouped is not None:
        return grouped.get(row_key, [])
    try:
        source_documents = list_source_documents(runtime_db_path(), row_key=row_key)
    except (OSError, sqlite3.Error):
        return []
    return source_document_evidence_payloads(row_key, source_documents)


def source_document_evidence_by_row_key() -> dict[str, list[dict[str, Any]]] | None:
    db_path = runtime_db_path()
    if not db_path.exists():
        return {}
    key = ("source_documents", str(db_path), path_mtime_ns(db_path))
    try:
        return cached_data(key, lambda: build_source_document_evidence_by_row_key(db_path))
    except (OSError, sqlite3.Error):
        return None


def build_source_document_evidence_by_row_key(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for source_document in list_source_documents(db_path):
        grouped.setdefault(source_document.row_key, []).append(source_document)
    return {row_key: source_document_evidence_payloads(row_key, documents) for row_key, documents in grouped.items()}


def source_document_evidence_payloads(row_key: str, source_documents: list[Any]) -> list[dict[str, Any]]:
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


def legacy_row_document_evidence(
    row: dict[str, Any],
    *,
    row_key: str,
    kimdis_documents: dict[str, dict[str, Any]] | None = None,
    authority_documents: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if row_key.startswith("KIMDIS:"):
        official_id = row_key.split(":", 1)[1]
        document = (kimdis_documents if kimdis_documents is not None else kimdis_documents_by_official_id()).get(official_id)
        if isinstance(document, dict):
            documents.append(document)
    else:
        documents.extend(
            document
            for document in (authority_documents if authority_documents is not None else authority_documents_by_key()).get(row_key, [])
            if isinstance(document, dict)
        )
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
            "dashboard": dashboard_payload(scope=dashboard_scope(scope)),
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
    dashboard = dashboard_payload(scope=dashboard_scope(scope))
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
        preflight = discovery_change_preflight()
        previous_success = latest_successful_discovery_run(discovery_history_path())
        backfill_already_complete = bool(
            backfill
            and previous_success
            and isinstance(previous_success.get("watermark"), dict)
            and previous_success["watermark"].get("complete") is True
        )
        if preflight.get("skip") and (not backfill or backfill_already_complete):
            if preflight.get("current"):
                save_source_fingerprint(preflight["current"])
            return {
                "ok": True,
                "skipped": True,
                "skip_reason": "SKIPPED_UNCHANGED_BACKFILL_COMPLETE" if backfill else "SKIPPED_UNCHANGED",
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
    health_by_id = source_health_by_id()
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
        health = health_by_id.get(source_id, source_health_from_latest_status(last_status, state.last_error if state else None))
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
                "health": health,
            }
        )

    latest_checked_values = [str(row["last_checked_at"]) for row in rows if row.get("last_checked_at")]
    warning_health = {"WATCH", "DEGRADED", "DISABLE_CANDIDATE"}
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
        "health_warning_total": sum(1 for row in rows if (row.get("health") or {}).get("status") in warning_health),
        "disable_candidate_total": sum(1 for row in rows if (row.get("health") or {}).get("status") == "DISABLE_CANDIDATE"),
        "last_checked_at": max(latest_checked_values, default=None),
    }
    return {
        "ok": True,
        "summary": summary,
        "rows": rows,
    }


def source_health_from_latest_status(status: str | None, error: str | None) -> dict[str, Any]:
    if status == "NEVER_CHECKED":
        return {
            "status": "UNKNOWN",
            "label": "Άγνωστο",
            "recent_checks": 0,
            "recent_failures": 0,
            "consecutive_failures": 0,
            "last_success_at": None,
            "recommendation": "Δεν έχει ελεγχθεί ακόμα.",
        }
    failed = status == "ERROR" or bool(error)
    return {
        "status": "WATCH" if failed else "HEALTHY",
        "label": "Παρακολούθηση" if failed else "Υγιής",
        "recent_checks": 1,
        "recent_failures": 1 if failed else 0,
        "consecutive_failures": 1 if failed else 0,
        "last_success_at": None,
        "recommendation": "Τελευταίος έλεγχος απέτυχε." if failed else "Τελευταίος έλεγχος επιτυχής.",
    }


def source_health_by_id(*, recent_limit: int = 20) -> dict[str, dict[str, Any]]:
    try:
        connection = sqlite3.connect(runtime_db_path())
        connection.row_factory = sqlite3.Row
        source_ids = [
            str(row["source_id"])
            for row in connection.execute("SELECT DISTINCT source_id FROM source_runs ORDER BY source_id").fetchall()
        ]
        result: dict[str, dict[str, Any]] = {}
        for source_id in source_ids:
            rows = connection.execute(
                """
                SELECT source_id, started_at, finished_at, status, error
                FROM source_runs
                WHERE source_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (source_id, max(1, int(recent_limit))),
            ).fetchall()
            result[source_id] = source_health_from_runs([dict(row) for row in rows])
        return result
    except (OSError, sqlite3.Error):
        return {}
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass


def source_health_from_runs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return source_health_from_latest_status("NEVER_CHECKED", None)
    recent_checks = len(rows)
    failed_rows = [row for row in rows if source_run_failed(row)]
    consecutive_failures = 0
    for row in rows:
        if source_run_failed(row):
            consecutive_failures += 1
            continue
        break
    last_success_at = next(
        (str(row.get("finished_at") or row.get("started_at") or "") for row in rows if not source_run_failed(row)),
        None,
    )
    failure_rate = len(failed_rows) / recent_checks if recent_checks else 0
    if consecutive_failures >= 5 or (recent_checks >= 10 and failure_rate >= 0.8):
        status = "DISABLE_CANDIDATE"
        label = "Υποψήφια αφαίρεση"
        recommendation = "Επαναλαμβανόμενες αποτυχίες. Θέλει χειροκίνητο έλεγχο ή προσωρινή απενεργοποίηση."
    elif consecutive_failures >= 2 or (recent_checks >= 5 and failure_rate >= 0.4):
        status = "DEGRADED"
        label = "Προβληματική"
        recommendation = "Συχνές αποτυχίες. Κράτα την πηγή, αλλά μην τη θεωρείς πλήρη κάλυψη."
    elif failed_rows:
        status = "WATCH"
        label = "Παρακολούθηση"
        recommendation = "Υπάρχουν πρόσφατες αποτυχίες, αλλά όχι αρκετές για αφαίρεση."
    else:
        status = "HEALTHY"
        label = "Υγιής"
        recommendation = "Οι πρόσφατοι έλεγχοι ολοκληρώθηκαν χωρίς σφάλματα."
    return {
        "status": status,
        "label": label,
        "recent_checks": recent_checks,
        "recent_failures": len(failed_rows),
        "consecutive_failures": consecutive_failures,
        "last_success_at": last_success_at,
        "recommendation": recommendation,
    }


def source_run_failed(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "") == "ERROR" or bool(row.get("error"))


def run_email_alerts(
    *,
    scope: str = "focus",
    sort: str = "deadline_asc",
    recipient: str | None = None,
    dry_run: bool = False,
    user_email: str | None = None,
) -> dict[str, Any]:
    payload = email_alerts_payload(scope=scope, sort=sort, recipient=recipient, dry_run=dry_run, user_email=user_email)
    if dry_run:
        return payload
    sent_at = utc_now_iso()
    sent_total = 0
    sent_email_total = 0
    for item in payload.get("per_recipient") or []:
        new_rows = item.get("new_rows") or []
        new_entalmata_rows = item.get("new_entalmata_rows") or []
        if not new_rows and not new_entalmata_rows:
            continue
        send_email_alert(str(item["recipient"]), str(item["subject"]), str(item["text_body"]), str(item["html_body"]))
        item["sent"] = len(new_rows) + len(new_entalmata_rows)
        item["sent_emails"] = 1
        sent_email_total += 1
        sent_total += item["sent"]
        for row in new_rows:
            record_notification_sent(
                runtime_db_path(),
                row_key=str(row["row_key"]),
                channel="email",
                recipient=str(item["recipient"]),
                subject=str(item["subject"]),
                sent_at=sent_at,
                metadata={
                    "display_id": row.get("display_id"),
                    "source_label": row.get("source_label"),
                    "official_url": row.get("official_url"),
                },
            )
        for row in new_entalmata_rows:
            record_notification_sent(
                runtime_db_path(),
                row_key=str(row["row_key"]),
                channel="entalmata_email",
                recipient=str(item["recipient"]),
                subject=str(item["subject"]),
                sent_at=sent_at,
                metadata={
                    "ada": row.get("ada"),
                    "document_url": row.get("document_url"),
                    "project_title": row.get("project_title"),
                },
            )
    payload["sent"] = sent_total
    payload["sent_emails"] = sent_email_total
    payload["sent_at"] = sent_at
    return payload


def entalmata_payload() -> dict[str, Any]:
    config_path = REPO_ROOT / "config/diavgeia_entalmata.yml"
    data = load_config(config_path)
    visible_days = int(data.get("visible_window_days") or 15)
    records = list_entalmata(runtime_db_path(), visible_window_days=visible_days)
    report_path = REPO_ROOT / "work/reports/diavgeia_entalmata_latest.json"
    latest_report = None
    if report_path.exists():
        try:
            latest_report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            latest_report = None
    return {
        "ok": True,
        "visible_window_days": visible_days,
        "organizations": data.get("organizations") or [],
        "keywords": data.get("keywords") or [],
        "summary": {
            "visible": len(records),
            "archived": archived_entalmata_count(runtime_db_path()),
            "configured_organizations": len(data.get("organizations") or []),
            "keywords": len(data.get("keywords") or []),
            "last_scan_at": (latest_report or {}).get("generated_at") or (latest_report or {}).get("cutoff_date"),
            "last_scan_summary": (latest_report or {}).get("summary"),
        },
        "records": [record.to_dict() for record in records],
    }


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
    entalmata_result = run_scheduled_entalmata_scan()
    if entalmata_result.get("ok") is False:
        warnings.append(
            {
                "stage": "entalmata_scan",
                "message": str(entalmata_result.get("error") or "entalmata scan failed"),
            }
        )
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
    source_rows = source_polling.get("rows") or []
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
            for row in source_rows
            if row.get("last_status") == "SKIPPED_UNCHANGED" and str(row.get("source_id") or "") not in changed_source_id_set
        ],
        "source_errors": [
            {"source_id": row.get("source_id"), "error": row.get("last_error")}
            for row in source_rows
            if row.get("last_error")
        ],
        "problem_sources": scheduled_problem_sources(source_rows),
        "discovery": summarize_scheduled_stage(discovery),
        "ai_triage": summarize_scheduled_stage(ai_result),
        "auto_document_fetch": summarize_scheduled_stage(auto_document_fetch),
        "enrichment": summarize_scheduled_stage(auto_document_fetch),
        "entalmata": summarize_scheduled_stage(entalmata_result),
        "email": summarize_email_result(email_result),
        "errors": errors,
        "warnings": warnings,
    }
    payload["coverage_metrics"] = scheduled_coverage_metrics(payload, source_rows=source_rows)
    payload["monitoring_alerts"] = scheduled_monitoring_alerts(payload)
    payload["monitoring_status"] = scheduled_monitoring_status(payload["monitoring_alerts"])
    try:
        payload["monitoring_email"] = send_scheduled_monitoring_alerts(payload, recipient=recipient, dry_run=dry_run)
    except Exception as exc:  # pragma: no cover - SMTP/runtime boundary
        payload["monitoring_email"] = {"ok": False, "error": str(exc), "sent": 0, "sent_emails": 0}
    if payload["monitoring_email"].get("ok") is False:
        warnings.append({"stage": "monitoring_email", "message": str(payload["monitoring_email"].get("error") or "monitoring alert email failed")})
        payload["warnings"] = warnings
    write_scheduled_run_reports(payload, report_path=report_path, markdown_report_path=markdown_report_path)
    return payload


def scheduled_coverage_metrics(payload: dict[str, Any], *, source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_summary = payload.get("source_polling_summary") or {}
    source_checked = [
        row
        for row in source_rows
        if str(row.get("last_status") or "").strip() and str(row.get("last_status") or "").strip() != "NEVER_CHECKED"
    ]
    email = payload.get("email") or {}
    entalmata = payload.get("entalmata") or {}
    entalmata_summary = entalmata.get("summary") or {}
    discovery = payload.get("discovery") or {}
    ai_triage = payload.get("ai_triage") or {}
    auto_document_fetch = payload.get("auto_document_fetch") or {}
    return {
        "sources_configured": int(source_summary.get("configured_total") or len(source_rows) or 0),
        "sources_checked": len(source_checked),
        "sources_changed": int(source_summary.get("changed_total") or 0),
        "sources_skipped_unchanged": int(source_summary.get("unchanged_total") or 0),
        "source_errors": int(source_summary.get("error_total") or len(payload.get("source_errors") or []) or 0),
        "source_health_warnings": int(source_summary.get("health_warning_total") or 0),
        "discovery_ok": discovery.get("ok"),
        "discovery_skipped": discovery.get("skipped"),
        "ai_triage_ok": ai_triage.get("ok"),
        "ai_triage_skipped": ai_triage.get("skipped"),
        "auto_document_fetch_ok": auto_document_fetch.get("ok"),
        "auto_document_fetch_skipped": auto_document_fetch.get("skipped"),
        "public_works_candidate_rows": int(email.get("candidate_rows") or 0),
        "public_works_new_email_rows": int(email.get("new_count") or 0),
        "public_works_already_emailed": int(email.get("skipped_already_sent") or 0),
        "entalmata_candidate_rows": int(email.get("entalmata_candidate_rows") or 0),
        "entalmata_new_email_rows": int(email.get("new_entalmata_count") or 0),
        "entalmata_already_emailed": int(email.get("entalmata_skipped_already_sent") or 0),
        "entalmata_matched": int(entalmata_summary.get("matched") or entalmata_summary.get("visible") or 0),
        "email_ok": email.get("ok"),
        "sent_items": int(email.get("sent") or 0),
        "sent_emails": int(email.get("sent_emails") or 0),
        "errors": len(payload.get("errors") or []),
        "warnings": len(payload.get("warnings") or []),
}


def scheduled_problem_sources(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for row in source_rows:
        health = row.get("health") if isinstance(row.get("health"), dict) else {}
        last_status = str(row.get("last_status") or "").strip()
        last_error = str(row.get("last_error") or "").strip()
        health_status = str(health.get("status") or "").strip()
        is_problem = bool(
            last_error
            or last_status == "ERROR"
            or health_status in {"WATCH", "DEGRADED", "DISABLE_CANDIDATE"}
        )
        if not is_problem:
            continue
        problems.append(
            {
                "source_id": row.get("source_id"),
                "name": row.get("name") or row.get("source_name") or row.get("source_id"),
                "family_or_adapter": row.get("family_or_adapter") or row.get("adapter"),
                "last_status": last_status or None,
                "last_error": last_error or None,
                "last_checked_at": row.get("last_checked_at"),
                "health_status": health_status or None,
                "recent_failures": health.get("recent_failures"),
                "consecutive_failures": health.get("consecutive_failures"),
                "recommendation": health.get("recommendation"),
            }
        )
    problems.sort(
        key=lambda item: (
            0 if item.get("last_error") or item.get("last_status") == "ERROR" else 1,
            str(item.get("source_id") or ""),
        )
    )
    return problems[:12]


def scheduled_monitoring_alerts(payload: dict[str, Any]) -> list[dict[str, str]]:
    metrics = payload.get("coverage_metrics") or {}
    alerts: list[dict[str, str]] = []

    def add(severity: str, code: str, message: str) -> None:
        alerts.append({"severity": severity, "code": code, "message": message})

    for item in payload.get("errors") or []:
        add("ERROR", f"STAGE_{str(item.get('stage') or 'unknown').upper()}", str(item.get("message") or "Scheduled stage failed."))
    if metrics.get("sources_configured") and not metrics.get("sources_checked"):
        add("ERROR", "NO_SOURCES_CHECKED", "No configured public-works source has a completed recent polling state.")
    if metrics.get("source_errors"):
        add("WARNING", "SOURCE_ERRORS", f"{metrics.get('source_errors')} source(s) reported errors in the latest polling state.")
    if metrics.get("source_health_warnings"):
        add("WARNING", "SOURCE_HEALTH_WARNINGS", f"{metrics.get('source_health_warnings')} source(s) are degraded or need attention.")
    if (payload.get("entalmata") or {}).get("ok") is False:
        add("WARNING", "ENTALMATA_SCAN_FAILED", str((payload.get("entalmata") or {}).get("error") or "Entalmata scan failed."))
    if (payload.get("auto_document_fetch") or {}).get("ok") is False:
        add("WARNING", "AUTO_DOCUMENT_FETCH_FAILED", "Automatic document fetch did not complete cleanly.")
    if metrics.get("public_works_new_email_rows") and not payload.get("dry_run") and not metrics.get("sent_emails"):
        add("ERROR", "EMAIL_NOT_SENT", "New public-works rows existed but no email was sent.")
    if (
        metrics.get("sources_changed")
        and not metrics.get("public_works_candidate_rows")
        and (payload.get("discovery") or {}).get("skipped") is not True
    ):
        add("WARNING", "ZERO_PUBLIC_WORKS_CANDIDATES", "Changed sources produced zero public-works dashboard candidates.")
    return alerts


def scheduled_monitoring_status(alerts: list[dict[str, str]]) -> str:
    if any(alert.get("severity") == "ERROR" for alert in alerts):
        return "ERROR"
    if alerts:
        return "WARNING"
    return "OK"


def send_scheduled_monitoring_alerts(
    payload: dict[str, Any],
    *,
    recipient: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    alerts = payload.get("monitoring_alerts") or []
    if not alerts:
        return {"ok": True, "skipped": True, "skip_reason": "NO_MONITORING_ALERTS", "sent": 0, "sent_emails": 0}
    targets = email_alert_recipients(recipient)
    if not targets:
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "skipped": True,
                "skip_reason": "DRY_RUN_RECIPIENT_NOT_CONFIGURED",
                "alerts": len(alerts),
                "sent": 0,
                "sent_emails": 0,
            }
        return {"ok": False, "error": "Monitoring alert recipient is not configured.", "sent": 0, "sent_emails": 0}
    signature_payload = {
        "date": str(payload.get("started_at") or "")[:10],
        "alerts": [(item.get("severity"), item.get("code"), item.get("message")) for item in alerts],
    }
    digest = hashlib.sha256(json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    row_key = f"SYSTEM_MONITOR:{signature_payload['date']}:{digest}"
    subject = f"Tender Radar monitoring: {payload.get('monitoring_status')}"
    text_body = render_scheduled_monitoring_alert_text(payload)
    html_body = render_scheduled_monitoring_alert_html(payload)
    sent = 0
    sent_emails = 0
    skipped = 0
    for target in targets:
        if notification_already_sent(runtime_db_path(), row_key=row_key, channel="monitoring_email", recipient=target):
            skipped += 1
            continue
        if not dry_run:
            send_email_alert(target, subject, text_body, html_body)
            record_notification_sent(
                runtime_db_path(),
                row_key=row_key,
                channel="monitoring_email",
                recipient=target,
                subject=subject,
                sent_at=utc_now_iso(),
                metadata={"monitoring_status": payload.get("monitoring_status"), "alerts": alerts},
            )
            sent += len(alerts)
            sent_emails += 1
    return {
        "ok": True,
        "dry_run": dry_run,
        "row_key": row_key,
        "recipient": targets[0],
        "recipients": targets,
        "alerts": len(alerts),
        "sent": sent,
        "sent_emails": sent_emails,
        "skipped_already_sent": skipped,
    }


def render_scheduled_monitoring_alert_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Tender Radar monitoring: {payload.get('monitoring_status')}",
        "",
        f"Started: {payload.get('started_at')}",
        f"Completed: {payload.get('completed_at')}",
        "",
        "Alerts:",
    ]
    for alert in payload.get("monitoring_alerts") or []:
        lines.append(f"- {alert.get('severity')} {alert.get('code')}: {alert.get('message')}")
    metrics = payload.get("coverage_metrics") or {}
    lines.extend(
        [
            "",
            "Coverage:",
            f"- Sources checked: {metrics.get('sources_checked')}/{metrics.get('sources_configured')}",
            f"- Source errors: {metrics.get('source_errors')}",
            f"- Public works candidates: {metrics.get('public_works_candidate_rows')}",
            f"- New public works email rows: {metrics.get('public_works_new_email_rows')}",
            f"- Entalmata candidates: {metrics.get('entalmata_candidate_rows')}",
            f"- Sent emails: {metrics.get('sent_emails')}",
        ]
    )
    problem_sources = payload.get("problem_sources") or []
    if problem_sources:
        lines.extend(["", "Problem sources:"])
        for source in problem_sources:
            status_bits = [
                str(source.get("last_status") or "UNKNOWN"),
                f"health={source.get('health_status')}" if source.get("health_status") else "",
                f"checked={source.get('last_checked_at')}" if source.get("last_checked_at") else "",
            ]
            detail = " · ".join(bit for bit in status_bits if bit)
            error = f" · error={source.get('last_error')}" if source.get("last_error") else ""
            lines.append(f"- {source.get('name') or source.get('source_id')} ({source.get('source_id')}): {detail}{error}")
    return "\n".join(lines)


def render_scheduled_monitoring_alert_html(payload: dict[str, Any]) -> str:
    alerts = "".join(
        f"<li><strong>{escape_html(alert.get('severity') or '')} {escape_html(alert.get('code') or '')}</strong>: {escape_html(alert.get('message') or '')}</li>"
        for alert in payload.get("monitoring_alerts") or []
    )
    metrics = payload.get("coverage_metrics") or {}
    coverage = (
        "<ul>"
        f"<li>Sources checked: {escape_html(metrics.get('sources_checked'))}/{escape_html(metrics.get('sources_configured'))}</li>"
        f"<li>Source errors: {escape_html(metrics.get('source_errors'))}</li>"
        f"<li>Public works candidates: {escape_html(metrics.get('public_works_candidate_rows'))}</li>"
        f"<li>New public works email rows: {escape_html(metrics.get('public_works_new_email_rows'))}</li>"
        f"<li>Entalmata candidates: {escape_html(metrics.get('entalmata_candidate_rows'))}</li>"
        f"<li>Sent emails: {escape_html(metrics.get('sent_emails'))}</li>"
        "</ul>"
    )
    problem_sources = "".join(
        "<li>"
        f"<strong>{escape_html(source.get('name') or source.get('source_id'))}</strong> "
        f"({escape_html(source.get('source_id'))})"
        f": {escape_html(source.get('last_status') or 'UNKNOWN')}"
        f"{' · health=' + escape_html(source.get('health_status')) if source.get('health_status') else ''}"
        f"{' · checked=' + escape_html(source.get('last_checked_at')) if source.get('last_checked_at') else ''}"
        f"{' · error=' + escape_html(source.get('last_error')) if source.get('last_error') else ''}"
        "</li>"
        for source in payload.get("problem_sources") or []
    )
    return (
        f"<h1>Tender Radar monitoring: {escape_html(payload.get('monitoring_status'))}</h1>"
        f"<p>Started: {escape_html(payload.get('started_at'))}<br>Completed: {escape_html(payload.get('completed_at'))}</p>"
        f"<h2>Alerts</h2><ul>{alerts}</ul>"
        f"<h2>Coverage</h2>{coverage}"
        f"{'<h2>Problem sources</h2><ul>' + problem_sources + '</ul>' if problem_sources else ''}"
    )


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
        "recipients": result.get("recipients"),
        "candidate_rows": result.get("candidate_rows"),
        "entalmata_candidate_rows": result.get("entalmata_candidate_rows"),
        "new_count": result.get("new_count"),
        "new_entalmata_count": result.get("new_entalmata_count"),
        "skipped_already_sent": result.get("skipped_already_sent"),
        "entalmata_skipped_already_sent": result.get("entalmata_skipped_already_sent"),
        "sent": result.get("sent"),
        "sent_emails": result.get("sent_emails"),
        "per_recipient": result.get("per_recipient"),
        "error": result.get("error"),
    }


def run_scheduled_entalmata_scan() -> dict[str, Any]:
    config_path = REPO_ROOT / "config/diavgeia_entalmata.yml"
    if not config_path.exists():
        return {"ok": True, "skipped": True, "skip_reason": "ENTALMATA_CONFIG_MISSING"}
    try:
        report = scan_entalmata(
            db_path=runtime_db_path(),
            config_path=config_path,
            download_dir=REPO_ROOT / "work/download_audit/diavgeia_entalmata",
        )
        report_path = REPO_ROOT / "work/reports/diavgeia_entalmata_latest.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    except Exception as exc:  # pragma: no cover - scheduled network/filesystem boundary
        return {"ok": False, "error": str(exc)}


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
    coverage = payload.get("coverage_metrics") or {}
    monitoring_alerts = payload.get("monitoring_alerts") or []
    lines = [
        "# Scheduled Poll and Alert",
        "",
        f"- Started: {payload.get('started_at')}",
        f"- Completed: {payload.get('completed_at')}",
        f"- Dry run: {payload.get('dry_run')}",
        f"- OK: {payload.get('ok')}",
        f"- Monitoring status: {payload.get('monitoring_status')}",
        "",
        "## Coverage",
        "",
        f"- Sources checked: {coverage.get('sources_checked')}/{coverage.get('sources_configured')}",
        f"- Source errors: {coverage.get('source_errors')}",
        f"- Source health warnings: {coverage.get('source_health_warnings')}",
        f"- Public works candidates: {coverage.get('public_works_candidate_rows')}",
        f"- New public works email rows: {coverage.get('public_works_new_email_rows')}",
        f"- Public works already emailed: {coverage.get('public_works_already_emailed')}",
        f"- Entalmata candidates: {coverage.get('entalmata_candidate_rows')}",
        f"- New entalmata email rows: {coverage.get('entalmata_new_email_rows')}",
        f"- Sent emails: {coverage.get('sent_emails')}",
        "",
        "## Monitoring Alerts",
        "",
    ]
    lines.extend(f"- {item.get('severity')} {item.get('code')}: {item.get('message')}" for item in monitoring_alerts)
    if not monitoring_alerts:
        lines.append("- none")
    problem_sources = payload.get("problem_sources") or []
    lines.extend(["", "## Problem Sources", ""])
    if problem_sources:
        for source in problem_sources:
            status_bits = [
                str(source.get("last_status") or "UNKNOWN"),
                f"health={source.get('health_status')}" if source.get("health_status") else "",
                f"checked={source.get('last_checked_at')}" if source.get("last_checked_at") else "",
            ]
            detail = " · ".join(bit for bit in status_bits if bit)
            error = f" · error={source.get('last_error')}" if source.get("last_error") else ""
            lines.append(f"- {source.get('name') or source.get('source_id')} ({source.get('source_id')}): {detail}{error}")
    else:
        lines.append("- none")
    lines.extend(
        [
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
            "## Entalmata",
            "",
            f"- OK: {(payload.get('entalmata') or {}).get('ok')}",
            f"- Skipped: {(payload.get('entalmata') or {}).get('skipped')}",
            f"- Summary: {json.dumps((payload.get('entalmata') or {}).get('summary') or {}, ensure_ascii=False)}",
            "",
            "## Email",
            "",
            f"- Candidate rows: {email.get('candidate_rows')}",
            f"- New rows: {email.get('new_count')}",
            f"- Already sent: {email.get('skipped_already_sent')}",
            f"- Entalmata candidate rows: {email.get('entalmata_candidate_rows')}",
            f"- New entalmata: {email.get('new_entalmata_count')}",
            f"- Entalmata already sent: {email.get('entalmata_skipped_already_sent')}",
            f"- Sent: {email.get('sent')}",
            f"- Sent emails: {email.get('sent_emails')}",
            f"- Recipients: {', '.join(email.get('recipients') or ([email.get('recipient')] if email.get('recipient') else []))}",
            "",
            "## Monitoring Email",
            "",
            f"- OK: {(payload.get('monitoring_email') or {}).get('ok')}",
            f"- Skipped: {(payload.get('monitoring_email') or {}).get('skipped')}",
            f"- Alerts: {(payload.get('monitoring_email') or {}).get('alerts')}",
            f"- Sent emails: {(payload.get('monitoring_email') or {}).get('sent_emails')}",
            "",
            "## Changed Sources",
            "",
        ]
    )
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
    user_email: str | None = None,
) -> dict[str, Any]:
    targets = email_alert_recipients(recipient)
    if not targets:
        raise ValueError("Email recipient is not configured. Set ALERT_EMAIL_TO or pass recipient.")
    entalmata_rows = entalmata_email_rows()
    per_recipient: list[dict[str, Any]] = []
    all_new_keys: set[str] = set()
    all_skipped_keys: set[str] = set()
    all_new_entalmata_keys: set[str] = set()
    all_skipped_entalmata_keys: set[str] = set()
    for target in targets:
        target_user_email = email_digest_user_email_for_recipient(
            target,
            explicit_user_email=user_email,
            explicit_recipient=recipient,
        )
        dashboard = dashboard_payload(scope=scope, sort=sort, user_email=target_user_email)
        rows = [email_alert_row(row) for row in dashboard.get("tenders") or []]
        rows = [row for row in rows if row["row_key"]]
        skipped = [
            row
            for row in rows
            if notification_already_sent(runtime_db_path(), row_key=row["row_key"], channel="email", recipient=target)
        ]
        skipped_keys = {row["row_key"] for row in skipped}
        new_rows = [row for row in rows if row["row_key"] not in skipped_keys]
        skipped_entalmata = [
            row
            for row in entalmata_rows
            if notification_already_sent(runtime_db_path(), row_key=row["row_key"], channel="entalmata_email", recipient=target)
        ]
        skipped_entalmata_keys = {row["row_key"] for row in skipped_entalmata}
        new_entalmata_rows = [row for row in entalmata_rows if row["row_key"] not in skipped_entalmata_keys]
        all_new_keys.update(row["row_key"] for row in new_rows)
        all_skipped_keys.update(row["row_key"] for row in skipped)
        all_new_entalmata_keys.update(row["row_key"] for row in new_entalmata_rows)
        all_skipped_entalmata_keys.update(row["row_key"] for row in skipped_entalmata)
        subject_parts = []
        if new_rows:
            subject_parts.append(f"{len(new_rows)} νέα έργα")
        if new_entalmata_rows:
            subject_parts.append(f"{len(new_entalmata_rows)} νέα εντάλματα")
        per_recipient.append(
            {
                "recipient": target,
                "new_count": len(new_rows),
                "skipped_already_sent": len(skipped),
                "new_entalmata_count": len(new_entalmata_rows),
                "entalmata_skipped_already_sent": len(skipped_entalmata),
                "new_rows": new_rows,
                "skipped_rows": skipped,
                "new_entalmata_rows": new_entalmata_rows,
                "skipped_entalmata_rows": skipped_entalmata,
                "subject": f"Tender Radar: {', '.join(subject_parts) if subject_parts else 'καμία νέα ειδοποίηση'}",
                "text_body": render_email_text(new_rows, entalmata_rows=new_entalmata_rows),
                "html_body": render_email_html(new_rows, entalmata_rows=new_entalmata_rows),
                "user_email": target_user_email,
                "user_interest_active": bool((dashboard.get("profile") or {}).get("user_interest_active")),
                "dashboard_summary": dashboard.get("summary") or {},
                "candidate_rows": len(rows),
                "sent": 0,
                "sent_emails": 0,
            }
        )
    representative = per_recipient[0]
    return {
        "ok": True,
        "dry_run": dry_run,
        "recipient": targets[0],
        "recipients": targets,
        "subject": representative["subject"],
        "dashboard_summary": representative.get("dashboard_summary") or {},
        "candidate_rows": sum(int(item.get("candidate_rows") or 0) for item in per_recipient),
        "entalmata_candidate_rows": len(entalmata_rows),
        "new_count": len(all_new_keys),
        "new_entalmata_count": len(all_new_entalmata_keys),
        "skipped_already_sent": len(all_skipped_keys),
        "entalmata_skipped_already_sent": len(all_skipped_entalmata_keys),
        "sent": 0,
        "sent_emails": 0,
        "new_rows": representative["new_rows"],
        "skipped_rows": representative["skipped_rows"],
        "new_entalmata_rows": representative["new_entalmata_rows"],
        "skipped_entalmata_rows": representative["skipped_entalmata_rows"],
        "text_body": representative["text_body"],
        "html_body": representative["html_body"],
        "per_recipient": per_recipient,
    }


def email_digest_user_email_for_recipient(
    target_recipient: str,
    *,
    explicit_user_email: str | None = None,
    explicit_recipient: str | None = None,
) -> str | None:
    normalized_recipient = target_recipient.strip().lower()
    normalized_explicit = (explicit_user_email or "").strip().lower()
    normalized_override = (explicit_recipient or "").strip().lower()
    if normalized_explicit and (not normalized_override or normalized_explicit == normalized_recipient):
        return normalized_explicit
    return normalized_recipient or normalized_explicit or None


def email_alert_row(row: dict[str, Any]) -> dict[str, Any]:
    row_key = str(row.get("row_key") or row.get("eshidis_id") or row.get("official_id") or row.get("display_id") or "")
    official_url = official_url_for_row(row)
    linked_ids = linked_eshidis_ids_for_row(row)
    return {
        "row_key": row_key,
        "display_id": row.get("display_id") or row.get("eshidis_id") or row.get("official_id"),
        "source_label": row.get("source_label"),
        "title": row.get("title"),
        "authority_name": row.get("authority_name"),
        "budget_display": row.get("budget_display"),
        "budget_sort": row.get("budget_sort"),
        "deadline_display": row.get("deadline_display"),
        "deadline_sort": row.get("deadline_sort"),
        "eshidis_id": row.get("eshidis_id"),
        "linked_eshidis_ids": linked_ids,
        "interest_reason": row.get("interest_reason"),
        "why_visible": row.get("why_visible") or [],
        "project_operations": row.get("project_operations") or [],
        "official_url": official_url,
    }


def email_row_reason(row: dict[str, Any]) -> str:
    for reason in row.get("why_visible") or []:
        if not isinstance(reason, dict):
            continue
        label = str(reason.get("label") or "").strip()
        text = str(reason.get("text") or "").strip()
        if text and label not in {"Πηγή", "Έγγραφα"}:
            return text
    return str(row.get("interest_reason") or "").strip()


def email_operation(row: dict[str, Any], label: str) -> dict[str, str] | None:
    for operation in row.get("project_operations") or []:
        if isinstance(operation, dict) and operation.get("label") == label:
            return {str(key): str(value) for key, value in operation.items()}
    return None


def email_row_has_documents(row: dict[str, Any]) -> bool:
    operation = email_operation(row, "Έγγραφα")
    if operation:
        return operation.get("status") == "ok"
    return False


def email_row_has_eshidis(row: dict[str, Any]) -> bool:
    return bool(str(row.get("eshidis_id") or "").strip() or row.get("linked_eshidis_ids"))


def email_deadline_days(row: dict[str, Any]) -> int | None:
    value = str(row.get("deadline_sort") or row.get("deadline_display") or "").strip()
    parsed = deadline_datetime(value)
    if not parsed:
        return None
    today = datetime.now(dashboard_timezone()).date()
    return (parsed.date() - today).days


def email_budget_value(row: dict[str, Any]) -> float | None:
    value = row.get("budget_sort")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def email_attention_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expiring = [row for row in rows if (days := email_deadline_days(row)) is not None and 0 <= days <= 7]
    missing_documents = [row for row in rows if not email_row_has_documents(row)]
    missing_eshidis = [row for row in rows if not email_row_has_eshidis(row)]
    with_budget = [row for row in rows if email_budget_value(row) is not None]
    highest_budget = sorted(with_budget, key=lambda item: email_budget_value(item) or 0, reverse=True)[:3]
    buckets = [
        {"title": "Λήγουν σύντομα", "rows": expiring},
        {"title": "Χωρίς έγγραφα", "rows": missing_documents},
        {"title": "Χωρίς ΕΣΗΔΗΣ", "rows": missing_eshidis},
        {"title": "Υψηλότεροι προϋπολογισμοί", "rows": highest_budget},
    ]
    return [bucket for bucket in buckets if bucket["rows"]]


def email_signal_labels(row: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    days = email_deadline_days(row)
    if days is not None and 0 <= days <= 7:
        labels.append("λήγει σύντομα")
    if not email_row_has_documents(row):
        labels.append("χωρίς έγγραφα")
    if not email_row_has_eshidis(row):
        labels.append("χωρίς ΕΣΗΔΗΣ")
    return labels


def entalmata_email_rows() -> list[dict[str, Any]]:
    config_path = REPO_ROOT / "config/diavgeia_entalmata.yml"
    visible_days = 15
    if config_path.exists():
        data = load_config(config_path)
        visible_days = int(data.get("visible_window_days") or visible_days)
    records = list_entalmata(runtime_db_path(), visible_window_days=visible_days)
    rows: list[dict[str, Any]] = []
    for record in records:
        ada = str(record.ada or "").strip()
        if not ada:
            continue
        rows.append(
            {
                "row_key": f"ENTALMA:{ada}",
                "ada": ada,
                "title": record.project_title or entalma_display_title(record),
                "subject": record.subject,
                "org_name": record.org_name,
                "issue_date": record.issue_date,
                "protocol_number": record.protocol_number,
                "document_url": record.document_url,
                "project_title": record.project_title,
                "matched_keywords": record.matched_keywords,
            }
        )
    return rows


def entalma_display_title(record: Any) -> str:
    protocol = str(getattr(record, "protocol_number", "") or "").strip()
    issue = str(getattr(record, "issue_date", "") or "").strip()
    if protocol or issue:
        return f"ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ {protocol}{('-' + issue) if issue else ''}".strip()
    return str(getattr(record, "subject", "") or getattr(record, "ada", "") or "Εντολή πληρωμής")


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


def render_email_text(rows: list[dict[str, Any]], *, entalmata_rows: list[dict[str, Any]] | None = None) -> str:
    entalmata_rows = entalmata_rows or []
    if not rows and not entalmata_rows:
        return "Δεν υπάρχουν νέες ειδοποιήσεις για αποστολή."
    lines: list[str] = []
    if rows:
        lines.extend(
            [
                "Tender Radar - Νέα έργα",
                "",
                f"Σύνολο νέων έργων: {len(rows)}",
                f"Λήγουν εντός 7 ημερών: {len([row for row in rows if (days := email_deadline_days(row)) is not None and 0 <= days <= 7])}",
                f"Χωρίς καταγεγραμμένα έγγραφα: {len([row for row in rows if not email_row_has_documents(row)])}",
                f"Χωρίς σύνδεση ΕΣΗΔΗΣ: {len([row for row in rows if not email_row_has_eshidis(row)])}",
                "",
                "Νέα έργα:",
                "",
            ]
        )
    for index, row in enumerate(rows, start=1):
        reason = email_row_reason(row)
        signals = ", ".join(email_signal_labels(row))
        lines.extend(
            [
                f"{index}. {row.get('title') or ''}",
                f"Α/Α: {row.get('display_id') or ''}",
                f"Πηγή: {row.get('source_label') or ''}",
                f"Φορέας: {row.get('authority_name') or ''}",
                f"Προϋπολογισμός: {row.get('budget_display') or ''}",
                f"Λήξη: {row.get('deadline_display') or ''}",
                f"Γιατί σε ενδιαφέρει: {reason or 'Δεν υπάρχει πρόσθετη αιτιολόγηση.'}",
                f"Σήματα: {signals or 'κανένα'}",
                f"Link: {row.get('official_url') or ''}",
                "",
            ]
        )
    buckets = email_attention_buckets(rows)
    if buckets:
        lines.extend(["Σήματα προσοχής:", ""])
        for bucket in buckets:
            lines.append(f"{bucket['title']}:")
            for row in bucket["rows"]:
                lines.append(f"- {row.get('display_id') or ''}: {row.get('title') or ''}")
            lines.append("")
    if entalmata_rows:
        if lines:
            lines.append("")
        lines.extend(["Νέα εντάλματα Tender Radar:", ""])
        for index, row in enumerate(entalmata_rows, start=1):
            lines.extend(
                [
                    f"{index}. {row.get('title') or ''}",
                    f"ΑΔΑ: {row.get('ada') or ''}",
                    f"Φορέας: {row.get('org_name') or ''}",
                    f"Ημερομηνία: {row.get('issue_date') or ''}",
                    f"Πρωτόκολλο: {row.get('protocol_number') or ''}",
                    f"Link PDF: {row.get('document_url') or ''}",
                    "",
                ]
            )
    return "\n".join(lines).strip()


def render_email_html(rows: list[dict[str, Any]], *, entalmata_rows: list[dict[str, Any]] | None = None) -> str:
    entalmata_rows = entalmata_rows or []
    if not rows and not entalmata_rows:
        return "<p>Δεν υπάρχουν νέες ειδοποιήσεις για αποστολή.</p>"
    sections: list[str] = []
    if rows:
        expiring_count = len([row for row in rows if (days := email_deadline_days(row)) is not None and 0 <= days <= 7])
        missing_documents_count = len([row for row in rows if not email_row_has_documents(row)])
        missing_eshidis_count = len([row for row in rows if not email_row_has_eshidis(row)])
        sections.append(
            "<h1>Tender Radar - Νέα έργα</h1>"
            "<ul>"
            f"<li>Σύνολο νέων έργων: {len(rows)}</li>"
            f"<li>Λήγουν εντός 7 ημερών: {expiring_count}</li>"
            f"<li>Χωρίς καταγεγραμμένα έγγραφα: {missing_documents_count}</li>"
            f"<li>Χωρίς σύνδεση ΕΣΗΔΗΣ: {missing_eshidis_count}</li>"
            "</ul>"
        )
    items = []
    for row in rows:
        link = row.get("official_url")
        title = escape_html(row.get("title") or "")
        title_html = f'<a href="{escape_html(link)}">{title}</a>' if link else title
        reason = escape_html(email_row_reason(row) or "Δεν υπάρχει πρόσθετη αιτιολόγηση.")
        signals = ", ".join(email_signal_labels(row)) or "κανένα"
        items.append(
            "<li>"
            f"<strong>{title_html}</strong><br>"
            f"Α/Α: {escape_html(row.get('display_id') or '')}<br>"
            f"Πηγή: {escape_html(row.get('source_label') or '')}<br>"
            f"Φορέας: {escape_html(row.get('authority_name') or '')}<br>"
            f"Προϋπολογισμός: {escape_html(row.get('budget_display') or '')}<br>"
            f"Λήξη: {escape_html(row.get('deadline_display') or '')}<br>"
            f"Γιατί σε ενδιαφέρει: {reason}<br>"
            f"Σήματα: {escape_html(signals)}"
            "</li>"
        )
    if items:
        sections.append("<h2>Νέα έργα</h2><ol>" + "".join(items) + "</ol>")
    bucket_items = []
    for bucket in email_attention_buckets(rows):
        links = "".join(
            f"<li>{escape_html(row.get('display_id') or '')}: {escape_html(row.get('title') or '')}</li>"
            for row in bucket["rows"]
        )
        bucket_items.append(f"<h3>{escape_html(bucket['title'])}</h3><ul>{links}</ul>")
    if bucket_items:
        sections.append("<h2>Σήματα προσοχής</h2>" + "".join(bucket_items))
    entalma_items = []
    for row in entalmata_rows:
        link = row.get("document_url")
        title = escape_html(row.get("title") or "")
        title_html = f'<a href="{escape_html(link)}">{title}</a>' if link else title
        entalma_items.append(
            "<li>"
            f"<strong>{title_html}</strong><br>"
            f"ΑΔΑ: {escape_html(row.get('ada') or '')}<br>"
            f"Φορέας: {escape_html(row.get('org_name') or '')}<br>"
            f"Ημερομηνία: {escape_html(row.get('issue_date') or '')}<br>"
            f"Πρωτόκολλο: {escape_html(row.get('protocol_number') or '')}"
            "</li>"
        )
    if entalma_items:
        sections.append("<h2>Νέα εντάλματα Tender Radar</h2><ol>" + "".join(entalma_items) + "</ol>")
    return "".join(sections)


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
    recipients = email_alert_recipients()
    return recipients[0] if recipients else None


def email_alert_recipients(recipient: str | None = None) -> list[str]:
    env = load_local_env()
    raw = (
        recipient
        or os.environ.get("ALERT_EMAIL_TO")
        or os.environ.get("EMAIL_ALERT_TO")
        or os.environ.get("EMAIL_TO")
        or env.get("ALERT_EMAIL_TO")
        or env.get("EMAIL_ALERT_TO")
        or env.get("EMAIL_TO")
    )
    if not raw:
        return []
    recipients: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;\n]+", raw):
        email = part.strip().lower()
        if not email or email in seen:
            continue
        recipients.append(email)
        seen.add(email)
    return recipients


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


ADMIN_SECRET_KEYS = ("TEE_USERNAME", "TEE_PASSWORD")


def admin_secrets_payload() -> dict[str, Any]:
    env = load_local_env()
    return {
        "ok": True,
        "path": ".env.local",
        "keys": {key: {"configured": bool(env.get(key))} for key in ADMIN_SECRET_KEYS},
    }


def update_admin_secrets(payload: dict[str, Any], *, actor_email: str | None = None) -> dict[str, Any]:
    updates: dict[str, str] = {}
    clear_keys: set[str] = set()
    for key in ADMIN_SECRET_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value)
        if not text:
            clear_keys.add(key)
            continue
        updates[key] = text
    if not updates and not clear_keys:
        raise ValueError("No secret values were provided.")
    write_local_env_values(updates, clear_keys=clear_keys)
    return {**admin_secrets_payload(), "updated": sorted(updates), "cleared": sorted(clear_keys), "actor_email": actor_email}


def user_interest_profile_payload(user_email: str) -> dict[str, Any]:
    stored = db_user_interest_profile(runtime_db_path(), user_email=user_email)
    profile = normalize_user_interest_profile((stored or {}).get("profile") if stored else {})
    return {
        "ok": True,
        "user_email": user_email.strip().lower(),
        "profile": profile,
        "category_options": public_works_taxonomy_profile_options(),
        "updated_at": (stored or {}).get("updated_at"),
        "active": user_interest_profile_is_active(profile),
    }


def update_user_interest_profile(user_email: str, payload: dict[str, Any]) -> dict[str, Any]:
    profile_payload = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
    profile = normalize_user_interest_profile(profile_payload)
    upsert_user_interest_profile(
        runtime_db_path(),
        user_email=user_email,
        profile=profile,
        metadata={"source": "ui"},
    )
    invalidate_ui_payload_cache()
    return user_interest_profile_payload(user_email)


def normalize_user_interest_profile(payload: object) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "include_keywords": normalize_profile_keyword_list(data.get("include_keywords")),
        "exclude_keywords": normalize_profile_keyword_list(data.get("exclude_keywords")),
        "category_ids": normalize_profile_category_ids(data.get("category_ids")),
        "min_budget": normalize_profile_budget(data.get("min_budget")),
        "max_budget": normalize_profile_budget(data.get("max_budget")),
    }


def normalize_profile_keyword_list(value: object) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,;]+", value)
    elif isinstance(value, list):
        raw_items = [str(item or "") for item in value]
    else:
        raw_items = []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        key = normalize_greek(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(text[:80])
        if len(cleaned) >= 40:
            break
    return cleaned


def normalize_profile_category_ids(value: object) -> list[str]:
    raw_items: list[str]
    if isinstance(value, str):
        raw_items = re.split(r"[\n,;]+", value)
    elif isinstance(value, list):
        raw_items = [str(item or "") for item in value]
    else:
        raw_items = []
    allowed = {str(item.get("id") or "") for item in public_works_taxonomy_profile_options()}
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        category_id = re.sub(r"[^a-zA-Z0-9_-]+", "", str(item or "").strip())
        if not category_id or category_id in seen:
            continue
        if allowed and category_id not in allowed:
            continue
        seen.add(category_id)
        cleaned.append(category_id)
        if len(cleaned) >= 30:
            break
    return cleaned


def normalize_profile_budget(value: object) -> float | None:
    if value in (None, ""):
        return None
    return budget_sort_value(value)


def user_interest_profile_is_active(profile: dict[str, Any]) -> bool:
    return bool(
        profile.get("include_keywords")
        or profile.get("exclude_keywords")
        or profile.get("category_ids")
        or profile.get("min_budget") is not None
        or profile.get("max_budget") is not None
    )


def write_local_env_values(updates: dict[str, str], *, clear_keys: set[str] | None = None) -> None:
    clear_keys = clear_keys or set()
    path = REPO_ROOT / ".env.local"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    written_keys: set[str] = set()
    output: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, _value = line.split("=", 1)
        clean_key = key.strip()
        if clean_key in clear_keys:
            written_keys.add(clean_key)
            continue
        if clean_key in updates:
            output.append(f"{clean_key}={env_file_quote(updates[clean_key])}")
            written_keys.add(clean_key)
            continue
        output.append(line)
    for key, value in updates.items():
        if key not in written_keys:
            output.append(f"{key}={env_file_quote(value)}")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def env_file_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


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


def require_admin_review_feedback_action(payload: dict[str, Any]) -> str:
    value = str(payload.get("action") or "").strip().upper()
    if value not in {"CONFIRM_DROP", "FORCE_KEEP"}:
        raise ValueError("Invalid admin review feedback action.")
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
    payload = cached_data(("candidates", str(path), path_mtime_ns(path)), lambda: json.loads(path.read_text(encoding="utf-8")))
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
    user_email: str | None = None,
    perform_expired_cleanup: bool = True,
) -> dict[str, Any]:
    safe_scope = dashboard_scope(scope)
    profile = location_focus_profile()
    user_profile_payload = user_interest_profile_payload(user_email) if user_email else None
    user_profile = (user_profile_payload or {}).get("profile") or {}
    overrides = triage_overrides_by_key(user_email=user_email)
    force_keep_keys = {key for key, item in overrides.items() if item.get("action") == "FORCE_KEEP"}
    confirmed_drop_keys = {key for key, item in overrides.items() if item.get("action") == "CONFIRM_DROP"}
    ignored = (ignored_tender_keys(user_email=user_email) | confirmed_drop_keys) - force_keep_keys
    triage = ai_triage_by_row_key() if apply_triage else {}
    rows = merged_tender_rows()
    rows = [row for row in rows if str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "") not in ignored]
    rows = [attach_ai_triage(row, triage, overrides=overrides) for row in rows]
    rows = rows_with_document_evidence(rows)
    canonical_rows, duplicate_hidden_rows = suppress_linked_eshidis_duplicates(rows)
    official_deadlines = official_eshidis_deadlines_by_id(canonical_rows)
    cleanup_report = (
        cleanup_expired_public_work_downloads(
            canonical_rows,
            as_of=as_of,
            official_deadlines=official_deadlines,
        )
        if perform_expired_cleanup
        else empty_expired_cleanup_report()
    )
    active_rows = [
        row
        for row in canonical_rows
        if dashboard_row_is_active(row, as_of=as_of, official_deadlines=official_deadlines)
    ]
    triage_hidden = [row for row in active_rows if row.get("ai_triage_hidden")]
    triage_visible_rows = [row for row in active_rows if not row.get("ai_triage_hidden")]
    visible_rows = [row for row in triage_visible_rows if row["interest_match"]]
    if user_interest_profile_is_active(user_profile):
        matched_rows = []
        for row in visible_rows:
            profile_match = user_profile_match_for_row(row, user_profile)
            if profile_match["matches"]:
                matched_rows.append({**row, "user_profile_match": profile_match})
        visible_rows = matched_rows
    else:
        visible_rows = [
            {**row, "user_profile_match": user_profile_match_for_row(row, user_profile)}
            for row in visible_rows
        ]
    visible_rows = sort_dashboard_rows(visible_rows, sort=sort)
    notifications = notification_logs_for_rows(visible_rows)
    visible_rows = [
        row_with_operational_explanation(row, notifications=notifications.get(row_key_for_tender(row), []))
        for row in visible_rows
    ]
    return {
        "scope": safe_scope,
        "sort": sort if sort in {"deadline_asc", "budget_desc"} else "deadline_asc",
        "profile": {
            **profile,
            "user_interest": user_profile,
            "user_interest_active": user_interest_profile_is_active(user_profile),
            "user_interest_updated_at": (user_profile_payload or {}).get("updated_at"),
        },
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
            "expired_download_cleanup": cleanup_report.get("summary") or {},
        },
        "tenders": visible_rows,
        "discovery_run": latest_discovery_run_payload(),
        "note": (
            "Focus filtering uses configured municipalities, regional units and NUTS hints. "
            "Discovery rows remain candidates until official detail/status verification."
        ),
    }


def notification_logs_for_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, object]]]:
    try:
        return notification_logs_by_row_key(
            runtime_db_path(),
            row_keys={row_key_for_tender(row) for row in rows},
            channel="email",
        )
    except (OSError, sqlite3.Error):
        return {}


def row_with_operational_explanation(row: dict[str, Any], *, notifications: list[dict[str, object]] | None = None) -> dict[str, Any]:
    notifications = notifications or []
    return {
        **row,
        "profile_fit": profile_fit_for_row(row),
        "ai_confidence_band": ai_confidence_band_for_row(row),
        "category_audit": category_audit_for_row(row),
        "project_identity": project_identity(row),
        "source_merge": source_merge_summary(row),
        "why_visible": why_visible_reasons(row),
        "project_sources": project_sources(row),
        "project_operations": project_operations(row, notifications=notifications),
        "project_timeline": project_timeline_events(row, notifications=notifications),
    }


def profile_fit_for_row(row: dict[str, Any]) -> dict[str, str]:
    user_match = row.get("user_profile_match") if isinstance(row.get("user_profile_match"), dict) else {}
    reason = str(row.get("interest_reason") or "").strip()
    if user_match.get("active"):
        details = [str(item) for item in user_match.get("reasons") or [] if str(item).strip()]
        return {
            "band": "USER_MATCH" if user_match.get("matches") else "USER_DROP",
            "label": "Ταιριάζει στο δικό σου προφίλ" if user_match.get("matches") else "Δεν ταιριάζει στο δικό σου προφίλ",
            "reason": "; ".join(details) or reason or "Εφαρμόστηκε προσωπικό προφίλ.",
        }
    if reason:
        return {
            "band": "MATCH",
            "label": "Ταιριάζει στο προφίλ",
            "reason": reason,
        }
    return {
        "band": "UNKNOWN",
        "label": "Χωρίς σαφές ταίριασμα προφίλ",
        "reason": "Δεν υπάρχει καταγεγραμμένη αιτιολόγηση περιοχής/προφίλ.",
    }


def user_profile_match_for_row(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    normalized_profile = normalize_user_interest_profile(profile)
    active = user_interest_profile_is_active(normalized_profile)
    if not active:
        return {"active": False, "matches": True, "reasons": []}
    haystack = normalize_greek(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "title",
                "authority_name",
                "display_id",
                "source_label",
                "interest_reason",
                "official_status_label",
            )
        )
    )
    include_keywords = normalized_profile.get("include_keywords") or []
    exclude_keywords = normalized_profile.get("exclude_keywords") or []
    category_ids = set(str(item) for item in normalized_profile.get("category_ids") or [])
    include_matches = [keyword for keyword in include_keywords if normalize_greek(keyword) in haystack]
    exclude_matches = [keyword for keyword in exclude_keywords if normalize_greek(keyword) in haystack]
    budget = row.get("budget_sort")
    try:
        budget_value = float(budget) if budget is not None else None
    except (TypeError, ValueError):
        budget_value = None
    reasons: list[str] = []
    matches = True
    if include_keywords:
        if include_matches:
            reasons.append(f"λέξεις ενδιαφέροντος: {', '.join(include_matches[:4])}")
        else:
            matches = False
            reasons.append("δεν βρέθηκε λέξη ενδιαφέροντος")
    if exclude_matches:
        matches = False
        reasons.append(f"αποκλείστηκε από: {', '.join(exclude_matches[:4])}")
    if category_ids:
        audit = category_audit_for_row(row)
        matched_categories = [
            label
            for label in audit.get("labels") or []
            if label.get("polarity") == "positive" and str(label.get("id") or "") in category_ids
        ]
        if matched_categories:
            reasons.append(
                "κατηγορίες έργων: "
                + ", ".join(str(label.get("label") or label.get("id") or "") for label in matched_categories[:4])
            )
        else:
            matches = False
            reasons.append("δεν ταιριάζει στις επιλεγμένες κατηγορίες έργων")
    min_budget = normalized_profile.get("min_budget")
    max_budget = normalized_profile.get("max_budget")
    if budget_value is None and (min_budget is not None or max_budget is not None):
        reasons.append("δεν υπάρχει καθαρός προϋπολογισμός για εφαρμογή ορίου")
    if budget_value is not None and min_budget is not None:
        if budget_value < float(min_budget):
            matches = False
            reasons.append(f"κάτω από ελάχιστο budget {format_budget(min_budget)}")
        else:
            reasons.append(f"πάνω από ελάχιστο budget {format_budget(min_budget)}")
    if budget_value is not None and max_budget is not None:
        if budget_value > float(max_budget):
            matches = False
            reasons.append(f"πάνω από μέγιστο budget {format_budget(max_budget)}")
        else:
            reasons.append(f"κάτω από μέγιστο budget {format_budget(max_budget)}")
    if not reasons:
        reasons.append("προσωπικό προφίλ χωρίς περιορισμούς που επηρεάζουν αυτό το έργο")
    return {"active": True, "matches": matches, "reasons": reasons}


def ai_confidence_band_for_row(row: dict[str, Any]) -> dict[str, str]:
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    decision = str(ai.get("decision") or "").strip()
    confidence = _float_or_none(ai.get("confidence"))
    keep = not bool(row.get("ai_triage_hidden"))
    if not ai or confidence is None:
        return {
            "band": "UNREVIEWED",
            "label": "Χωρίς AI band",
            "reason": "Δεν υπάρχει διαθέσιμη AI αξιολόγηση για αυτό το έργο.",
        }
    if keep and confidence >= 0.9:
        band = "SURE_MATCH"
        label = "Σίγουρο έργο"
    elif keep and confidence >= 0.75:
        band = "LIKELY_MATCH"
        label = "Μάλλον έργο"
    elif keep:
        band = "NEEDS_REVIEW"
        label = "Θέλει έλεγχο"
    elif confidence >= 0.9:
        band = "SURE_DROP"
        label = "Σίγουρα άσχετο"
    elif confidence >= 0.75:
        band = "LIKELY_DROP"
        label = "Μάλλον άσχετο"
    else:
        band = "NEEDS_REVIEW"
        label = "Θέλει έλεγχο"
    return {
        "band": band,
        "label": label,
        "reason": f"{decision} με confidence {confidence:.2f}".strip(),
    }


def public_works_taxonomy_config() -> dict[str, Any]:
    path = REPO_ROOT / "config" / "public_works_taxonomy.yml"
    if not path.exists():
        return {"version": 0, "categories": []}
    data = cached_data(("public_works_taxonomy", str(path), path_mtime_ns(path)), lambda: load_config(path))
    return data if isinstance(data, dict) else {"version": 0, "categories": []}


def public_works_taxonomy_profile_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for category in public_works_taxonomy_config().get("categories") or []:
        if not isinstance(category, dict) or category.get("negative_weight"):
            continue
        category_id = str(category.get("id") or "").strip()
        label = str(category.get("label") or category_id).strip()
        if category_id and label:
            options.append({"id": category_id, "label": label, "polarity": "positive"})
    return options


def category_audit_for_row(row: dict[str, Any]) -> dict[str, Any]:
    config = public_works_taxonomy_config()
    thresholds = config.get("confidence") if isinstance(config.get("confidence"), dict) else {}
    strong_threshold = float(thresholds.get("strong") or 0.85)
    likely_threshold = float(thresholds.get("likely") or 0.6)
    labels: list[dict[str, Any]] = []
    for category in config.get("categories") or []:
        if not isinstance(category, dict):
            continue
        label = category_match_for_row(row, category)
        if label:
            labels.append(label)
    labels.sort(key=lambda item: (0 if item.get("polarity") == "positive" else 1, -float(item.get("confidence") or 0), str(item.get("label") or "")))
    positive = [item for item in labels if item.get("polarity") == "positive"]
    negative = [item for item in labels if item.get("polarity") == "negative"]
    top_confidence = max((float(item.get("confidence") or 0) for item in labels), default=0.0)
    needs_review = bool(not positive or top_confidence < strong_threshold or (positive and negative))
    if not labels:
        summary = "Δεν βρέθηκε αρκετό taxonomy evidence. Θέλει ανθρώπινο έλεγχο."
        band = "UNKNOWN_REVIEW"
    elif needs_review:
        summary = "Βρέθηκαν ενδείξεις κατηγορίας, αλλά χρειάζεται έλεγχος πριν χρησιμοποιηθεί ως φίλτρο."
        band = "NEEDS_REVIEW"
    elif top_confidence >= strong_threshold:
        summary = "Η κατηγοριοποίηση έχει ισχυρά τεκμήρια."
        band = "STRONG"
    elif top_confidence >= likely_threshold:
        summary = "Η κατηγοριοποίηση έχει πιθανές ενδείξεις."
        band = "LIKELY"
    else:
        summary = "Η κατηγοριοποίηση είναι αδύναμη και χρειάζεται έλεγχο."
        band = "NEEDS_REVIEW"
    return {
        "version": config.get("version") or 0,
        "labels": labels,
        "primary": positive[0] if positive else (labels[0] if labels else None),
        "negative_labels": negative,
        "needs_review": needs_review,
        "band": band,
        "summary": summary,
    }


def category_match_for_row(row: dict[str, Any], category: dict[str, Any]) -> dict[str, Any] | None:
    signals = category.get("signals") if isinstance(category.get("signals"), dict) else {}
    evidence: list[dict[str, str]] = []
    score = 0.0
    haystack = taxonomy_haystack(row)
    cpv_text = taxonomy_cpv_text(row)
    for prefix in signals.get("cpv_prefixes") or []:
        prefix_text = str(prefix or "").strip()
        if prefix_text and prefix_text in cpv_text:
            score += 2.0
            evidence.append({"kind": "CPV", "text": prefix_text})
    for term in signals.get("strong_terms") or []:
        term_text = str(term or "").strip()
        if term_text and taxonomy_term_match(term_text, haystack):
            score += 2.0
            evidence.append({"kind": "ισχυρό σήμα", "text": term_text})
    for term in signals.get("medium_terms") or []:
        term_text = str(term or "").strip()
        if term_text and taxonomy_term_match(term_text, haystack):
            score += 1.0
            evidence.append({"kind": "μέτριο σήμα", "text": term_text})
    if score <= 0:
        return None
    weight = float(category.get("positive_weight") or category.get("negative_weight") or 2.0)
    confidence = min(0.99, score / max(3.0, weight * 2.0))
    polarity = "negative" if category.get("negative_weight") else "positive"
    return {
        "id": str(category.get("id") or ""),
        "label": str(category.get("label") or category.get("id") or ""),
        "polarity": polarity,
        "confidence": round(confidence, 2),
        "evidence": evidence[:8],
    }


def taxonomy_haystack(row: dict[str, Any]) -> str:
    return normalize_greek(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "title",
                "authority_name",
                "region",
                "row_text",
                "text_sample",
                "interest_reason",
                "official_status_label",
            )
        )
    ).replace("ς", "σ")


def taxonomy_cpv_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in ("cpv", "cpv_code", "cpv_codes", "row_text"))


def taxonomy_term_match(term: str, haystack: str) -> bool:
    normalized = normalize_greek(term).replace("ς", "σ")
    return bool(normalized and normalized in haystack)


def project_identity(row: dict[str, Any]) -> dict[str, Any]:
    eshidis_id = str(row.get("eshidis_id") or "").strip()
    linked_ids = linked_eshidis_ids_for_row(row)
    verified_ids = [str(value) for value in row.get("verified_eshidis_ids") or [] if str(value).strip().isdigit()]
    canonical_eshidis_id = eshidis_id or (verified_ids[0] if verified_ids else "") or (linked_ids[0] if linked_ids else "")
    official_id = str(row.get("official_id") or row.get("display_id") or "").strip()
    if canonical_eshidis_id:
        canonical_key = f"ESHIDIS:{canonical_eshidis_id}"
        canonical_label = f"ΕΣΗΔΗΣ {canonical_eshidis_id}"
        best_url = official_resource_url(canonical_eshidis_id)
    elif is_kimdis_identifier(official_id):
        canonical_key = f"KIMDIS:{official_id}"
        canonical_label = f"ΚΗΜΔΗΣ {official_id}"
        best_url = str(row.get("official_url") or row.get("attachment_url") or "")
    else:
        row_key = row_key_for_tender(row)
        canonical_key = row_key
        canonical_label = f"{row.get('source_label') or 'Πηγή'} {row.get('display_id') or official_id or row_key}".strip()
        best_url = str(row.get("official_url") or row.get("attachment_url") or row.get("download_url") or "")
    return {
        "canonical_key": canonical_key,
        "canonical_label": canonical_label,
        "primary_source": "ΕΣΗΔΗΣ" if canonical_eshidis_id else (row.get("source_label") or row.get("source") or ""),
        "preferred_eshidis_id": canonical_eshidis_id,
        "official_id": official_id,
        "best_url": best_url,
    }


def source_merge_summary(row: dict[str, Any]) -> dict[str, Any]:
    source_label = str(row.get("source_label") or "")
    linked_ids = linked_eshidis_ids_for_row(row)
    verified_ids = [str(value) for value in row.get("verified_eshidis_ids") or [] if str(value).strip().isdigit()]
    inbound_links = row.get("verified_source_links") if isinstance(row.get("verified_source_links"), list) else []
    status = str(row.get("verified_eshidis_link_status") or "").strip()
    if source_label == "ΕΣΗΔΗΣ":
        if inbound_links:
            return {
                "level": "LEVEL_1_OFFICIAL_CROSS_REFERENCE",
                "status": "CANONICAL_WITH_LINKED_SOURCES",
                "label": "Κύρια εγγραφή ΕΣΗΔΗΣ με συνδεδεμένες πηγές",
                "reason": f"{len(inbound_links)} πηγή/ές δείχνουν σε αυτή την επίσημη εγγραφή ΕΣΗΔΗΣ.",
                "linked_source_count": len(inbound_links),
            }
        return {
            "level": "LEVEL_0_SAME_SOURCE_RECORD",
            "status": "CANONICAL_SOURCE",
            "label": "Κύρια εγγραφή ΕΣΗΔΗΣ",
            "reason": "Η γραμμή είναι επίσημη εγγραφή ΕΣΗΔΗΣ.",
            "linked_source_count": 0,
        }
    if verified_ids:
        return {
            "level": "LEVEL_1_OFFICIAL_CROSS_REFERENCE",
            "status": status or "VERIFIED_ESHIDIS_LINK",
            "label": "Συνδεδεμένο με ΕΣΗΔΗΣ",
            "reason": f"Η πηγή έχει επαληθευμένη σύνδεση με ΕΣΗΔΗΣ {', '.join(verified_ids)}.",
            "linked_eshidis_ids": verified_ids,
        }
    if linked_ids:
        return {
            "level": "LEVEL_1_OFFICIAL_CROSS_REFERENCE",
            "status": status or "EXTRACTED_ESHIDIS_LINK",
            "label": "Βρέθηκε αριθμός ΕΣΗΔΗΣ",
            "reason": f"Εξήχθη αριθμός ΕΣΗΔΗΣ {', '.join(linked_ids)} από επίσημο κείμενο/έγγραφο.",
            "linked_eshidis_ids": linked_ids,
        }
    return {
        "level": "UNLINKED_SOURCE_RECORD",
        "status": status or "NO_ESHIDIS_LINK",
        "label": "Ανεξάρτητη πηγή",
        "reason": "Δεν υπάρχει ακόμα επαληθευμένη σύνδεση με άλλη επίσημη πηγή.",
        "linked_eshidis_ids": [],
    }


def project_sources(row: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []

    def add(
        label: str,
        identifier: str = "",
        url: str = "",
        status: str = "",
        primary: bool = False,
        role: str = "",
        merge_level: str = "",
    ) -> None:
        item = {
            "label": label,
            "identifier": identifier,
            "url": url,
            "status": status,
            "primary": "true" if primary else "false",
            "role": role,
            "merge_level": merge_level,
        }
        key = (item["label"], item["identifier"], item["url"])
        if not item["label"] or any((src["label"], src["identifier"], src["url"]) == key for src in sources):
            return
        sources.append(item)

    source_label = str(row.get("source_label") or row.get("source") or "Πηγή").strip()
    display_id = str(row.get("display_id") or row.get("official_id") or row.get("eshidis_id") or "").strip()
    add(
        source_label,
        display_id,
        str(row.get("official_url") or row.get("source_url") or row.get("attachment_url") or ""),
        "primary",
        True,
        "canonical" if source_label == "ΕΣΗΔΗΣ" else "source record",
        "LEVEL_0_SAME_SOURCE_RECORD",
    )

    eshidis_id = str(row.get("eshidis_id") or "").strip()
    for linked_id in [eshidis_id, *linked_eshidis_ids_for_row(row)]:
        linked_id = str(linked_id or "").strip()
        if linked_id.isdigit():
            add(
                "ΕΣΗΔΗΣ",
                linked_id,
                official_resource_url(linked_id),
                "official" if linked_id == eshidis_id else "linked",
                primary=linked_id == eshidis_id and source_label == "ΕΣΗΔΗΣ",
                role="canonical" if linked_id == eshidis_id else "linked official",
                merge_level="LEVEL_1_OFFICIAL_CROSS_REFERENCE" if linked_id != eshidis_id else "LEVEL_0_SAME_SOURCE_RECORD",
            )

    official_id = str(row.get("official_id") or "").strip()
    if is_kimdis_identifier(official_id):
        add("ΚΗΜΔΗΣ", official_id, str(row.get("official_url") or row.get("attachment_url") or ""), "notice", role="notice")

    for link in row.get("verified_source_links") or []:
        if not isinstance(link, dict):
            continue
        add(
            str(link.get("source_label") or "Συνδεδεμένη πηγή"),
            str(link.get("source_identifier") or ""),
            str(link.get("source_url") or ""),
            str(link.get("verification_status") or "verified link"),
            role="linked source",
            merge_level="LEVEL_1_OFFICIAL_CROSS_REFERENCE",
        )
    return sources


def project_operations(row: dict[str, Any], *, notifications: list[dict[str, object]]) -> list[dict[str, str]]:
    operations: list[dict[str, str]] = []
    document_count = int(row.get("document_evidence_count") or row.get("local_document_count") or 0)
    if document_count:
        operations.append({"label": "Έγγραφα", "status": "ok", "text": f"{document_count} έγγραφα έχουν καταγραφεί/είναι διαθέσιμα."})
    elif row.get("has_local_documents"):
        operations.append({"label": "Έγγραφα", "status": "ok", "text": "Υπάρχουν τοπικά αρχεία για preview/zip."})
    else:
        operations.append({"label": "Έγγραφα", "status": "pending", "text": "Δεν έχουν καταγραφεί ακόμα τοπικά έγγραφα."})

    if notifications:
        recipients = sorted({str(item.get("recipient") or "") for item in notifications if item.get("recipient")})
        latest = max((str(item.get("sent_at") or "") for item in notifications), default="")
        operations.append(
            {
                "label": "Email",
                "status": "sent",
                "text": f"Στάλθηκε σε {len(recipients)} παραλήπτη/ες." + (f" Τελευταίο: {latest}." if latest else ""),
            }
        )
    else:
        operations.append({"label": "Email", "status": "pending", "text": "Δεν έχει καταγραφεί αποστολή email για αυτό το έργο."})

    override = row.get("triage_override") if isinstance(row.get("triage_override"), dict) else {}
    if override:
        scope = "χρήστη" if override.get("scope") == "user" else "global"
        operations.append(
            {
                "label": "Feedback",
                "status": str(override.get("action") or ""),
                "text": f"{override.get('action') or 'override'} ({scope})" + (f": {override.get('reason')}" if override.get("reason") else ""),
            }
        )

    deadline = str(row.get("deadline_display") or "").strip()
    if deadline:
        operations.append({"label": "Cleanup", "status": "scheduled", "text": "Τα μεγάλα downloaded αρχεία καθαρίζονται αυτόματα μετά τη λήξη."})
    return operations


def why_visible_reasons(row: dict[str, Any]) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    source_label = str(row.get("source_label") or row.get("source") or "πηγή").strip()
    display_id = str(row.get("display_id") or row.get("eshidis_id") or row.get("official_id") or "").strip()
    source_text = f"{source_label} {display_id}".strip()
    if source_text:
        reasons.append({"label": "Πηγή", "text": f"Εντοπίστηκε από {source_text}."})

    interest = str(row.get("interest_reason") or "").strip()
    if interest:
        reasons.append({"label": "Περιοχή", "text": f"Ταιριάζει με {interest}."})

    status_label = str(row.get("official_status_label") or "").strip()
    if status_label:
        reasons.append({"label": "Σύνδεση", "text": status_label})

    deadline = str(row.get("deadline_display") or "").strip()
    if deadline:
        if row.get("deadline_verification_status") == "DOCUMENT_DEADLINE_EVIDENCE":
            reasons.append({"label": "Προθεσμία", "text": f"Ενεργή προθεσμία από κατεβασμένα έγγραφα: {deadline}."})
        else:
            reasons.append({"label": "Προθεσμία", "text": f"Ενεργή προθεσμία: {deadline}."})

    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    if ai:
        decision = str(ai.get("decision") or "").strip()
        confidence = ai.get("confidence")
        suffix = f" με confidence {confidence}" if confidence not in (None, "") else ""
        if decision:
            reasons.append({"label": "AI", "text": f"Κρατήθηκε από AI ως {decision}{suffix}."})
        elif ai.get("reason"):
            reasons.append({"label": "AI", "text": str(ai.get("reason"))})

    document_count = int(row.get("document_evidence_count") or 0)
    if document_count:
        reasons.append({"label": "Έγγραφα", "text": f"Υπάρχουν {document_count} κατεβασμένα/ελεγμένα έγγραφα πηγής."})
    elif row.get("has_local_documents"):
        reasons.append({"label": "Έγγραφα", "text": "Υπάρχουν τοπικά αρχεία για αυτό το έργο."})

    return reasons


def project_timeline_events(row: dict[str, Any], *, notifications: list[dict[str, object]] | None = None) -> list[dict[str, str]]:
    notifications = notifications or []
    events: list[dict[str, str]] = []
    source_label = str(row.get("source_label") or row.get("source") or "πηγή").strip()
    display_id = str(row.get("display_id") or row.get("eshidis_id") or row.get("official_id") or "").strip()
    discovered_at = str(row.get("discovered_at") or row.get("published_at") or row.get("retrieved_at") or "").strip()
    events.append(
        {
            "label": "Εντοπισμός",
            "text": f"{source_label} {display_id}".strip() or "Εντοπίστηκε από διαθέσιμη πηγή.",
            "at": discovered_at,
        }
    )

    interest = str(row.get("interest_reason") or "").strip()
    if interest:
        events.append({"label": "Φίλτρο ενδιαφέροντος", "text": interest, "at": ""})

    linked_ids = linked_eshidis_ids_for_row(row)
    eshidis_id = str(row.get("eshidis_id") or "").strip()
    if eshidis_id or linked_ids:
        ids = ", ".join([eshidis_id, *[value for value in linked_ids if value != eshidis_id]]).strip(", ")
        events.append({"label": "ΕΣΗΔΗΣ", "text": f"Σύνδεση με Α/Α {ids}.", "at": ""})

    source_merge = source_merge_summary(row)
    if source_merge.get("level") == "LEVEL_1_OFFICIAL_CROSS_REFERENCE":
        events.append(
            {
                "label": "Ενοποίηση πηγών",
                "text": f"{source_merge.get('label')}: {source_merge.get('reason')}",
                "at": "",
            }
        )

    deadline = str(row.get("deadline_display") or "").strip()
    if deadline:
        source = "από έγγραφα" if row.get("deadline_verification_status") == "DOCUMENT_DEADLINE_EVIDENCE" else "από επίσημη εγγραφή"
        events.append({"label": "Προθεσμία", "text": f"{deadline} ({source}).", "at": ""})

    document_count = int(row.get("document_evidence_count") or 0)
    if document_count:
        events.append({"label": "Έγγραφα", "text": f"{document_count} έγγραφα διαθέσιμα στο σύστημα.", "at": ""})

    if notifications:
        latest = max((str(item.get("sent_at") or "") for item in notifications), default="")
        recipients = sorted({str(item.get("recipient") or "") for item in notifications if item.get("recipient")})
        events.append({"label": "Email", "text": f"Στάλθηκε σε {len(recipients)} παραλήπτη/ες.", "at": latest})

    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    if ai:
        reason = str(ai.get("reason") or ai.get("decision") or "").strip()
        events.append({"label": "AI έλεγχος", "text": reason, "at": str(ai.get("triage_generated_at") or "")})

    override = row.get("triage_override") if isinstance(row.get("triage_override"), dict) else {}
    if override:
        scope = "χρήστη" if override.get("scope") == "user" else "global"
        text = f"{override.get('action') or 'override'} ({scope})"
        if override.get("reason"):
            text = f"{text}: {override.get('reason')}"
        events.append({"label": "Feedback", "text": text, "at": str(override.get("created_at") or "")})

    return events


def reverse_search_payload(payload: dict[str, Any], *, user_email: str | None = None) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if len(query) < 2:
        return {
            "ok": True,
            "query": query,
            "summary": {"active_rows_searched": 0, "matches": 0, "document_matches": 0},
            "results": [],
            "empty_message": "Γράψε τουλάχιστον 2 χαρακτήρες για αναζήτηση.",
        }
    dashboard = dashboard_payload(scope="focus", sort="deadline_asc", user_email=user_email)
    rows = [row for row in dashboard.get("tenders") or [] if isinstance(row, dict)]
    docs_by_eshidis = reverse_search_documents_by_eshidis(rows)
    results: list[dict[str, Any]] = []
    document_match_count = 0
    for row in rows:
        matches = reverse_search_matches_for_row(row, query=query, docs_by_eshidis=docs_by_eshidis)
        if not matches:
            continue
        document_match_count += sum(1 for match in matches if match.get("kind") == "document")
        results.append(
            {
                "row_key": row_key_for_tender(row),
                "display_id": row.get("display_id"),
                "source_label": row.get("source_label"),
                "title": row.get("title"),
                "authority_name": row.get("authority_name") or row.get("authority"),
                "region": row.get("region"),
                "budget_display": row.get("budget_display"),
                "deadline_display": row.get("deadline_display"),
                "official_url": row.get("official_url"),
                "matches": matches[:MAX_REVERSE_DOCUMENT_MATCHES_PER_ROW],
            }
        )
        if len(results) >= MAX_REVERSE_SEARCH_RESULTS:
            break
    return {
        "ok": True,
        "query": query,
        "summary": {
            "active_rows_searched": len(rows),
            "matches": len(results),
            "document_matches": document_match_count,
            "result_limit": MAX_REVERSE_SEARCH_RESULTS,
        },
        "results": results,
        "empty_message": "Δεν βρέθηκε ενεργό έργο με αυτή τη λέξη ή φράση." if not results else None,
    }


def pricing_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if len(query) < 2:
        return {
            "ok": True,
            "query": query,
            "summary": {"matches": 0},
            "results": [],
            "empty_message": "Γράψε άρθρο, περιγραφή ή κωδικό αναθεώρησης.",
        }
    limit = min(max(int(payload.get("limit") or 50), 1), 200)
    return search_pricing_rows(runtime_db_path(), query, limit=limit)


def pricing_ingest_status_payload() -> dict[str, Any]:
    db_path = runtime_db_path()
    if not db_path.exists():
        return {"ok": True, "exists": False, "run": None, "summary": {}}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            """
            SELECT run_id, mode, started_at, finished_at, status, summary_json
              FROM pricing_runs
             ORDER BY started_at DESC
             LIMIT 1
            """
        ).fetchone()
        if run is None:
            return {"ok": True, "exists": False, "run": None, "summary": {}}
        summary = json.loads(run["summary_json"] or "{}")
        live_counts = pricing_live_counts_for_run(connection, started_at=str(run["started_at"] or ""))
        return {
            "ok": True,
            "exists": True,
            "run": {
                "run_id": run["run_id"],
                "mode": run["mode"],
                "started_at": run["started_at"],
                "finished_at": run["finished_at"],
                "status": run["status"],
            },
            "summary": summary if isinstance(summary, dict) else {},
            "live_counts": live_counts,
        }
    except sqlite3.OperationalError:
        return {"ok": True, "exists": False, "run": None, "summary": {}, "live_counts": {}}
    finally:
        connection.close()


def pricing_live_counts_for_run(connection: sqlite3.Connection, *, started_at: str) -> dict[str, Any]:
    if not started_at:
        return {}
    projects = connection.execute(
        """
        SELECT COUNT(*) AS projects
          FROM pricing_projects
         WHERE first_seen_at >= ?
        """,
        (started_at,),
    ).fetchone()[0]
    documents = connection.execute(
        """
        SELECT COUNT(*) AS documents
          FROM pricing_documents
         WHERE fetched_at >= ?
        """,
        (started_at,),
    ).fetchone()[0]
    text_docs = connection.execute(
        """
        SELECT COUNT(*) AS text_docs
          FROM pricing_documents
         WHERE fetched_at >= ?
           AND text_path IS NOT NULL
        """,
        (started_at,),
    ).fetchone()[0]
    merged_rows = connection.execute(
        """
        SELECT COUNT(*) AS merged_rows
          FROM pricing_budget_rows
         WHERE source_document = ?
           AND extracted_at >= ?
        """,
        ("__PROJECT_BUDGET_MERGED__", started_at),
    ).fetchone()[0]
    latest_projects = connection.execute(
        """
        SELECT eshidis_id, title, deadline_at
          FROM pricing_projects
         WHERE first_seen_at >= ?
         ORDER BY first_seen_at DESC
         LIMIT 5
        """,
        (started_at,),
    ).fetchall()
    return {
        "projects": int(projects or 0),
        "documents": int(documents or 0),
        "text_docs": int(text_docs or 0),
        "merged_rows": int(merged_rows or 0),
        "latest_projects": [dict(row) for row in latest_projects],
    }


def reverse_search_documents_by_eshidis(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    eshidis_ids = {
        str(row.get("eshidis_id") or row.get("display_id") or "").strip()
        for row in rows
        if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ"
    }
    eshidis_ids = {value for value in eshidis_ids if value.isdigit()}
    if not eshidis_ids:
        return {}
    try:
        documents = list_searchable_documents(runtime_db_path())
    except (OSError, sqlite3.Error):
        return {}
    by_eshidis: dict[str, list[Any]] = {}
    for document in documents:
        eshidis_id = str(getattr(document, "eshidis_id", "") or "").strip()
        if eshidis_id in eshidis_ids:
            by_eshidis.setdefault(eshidis_id, []).append(document)
    return by_eshidis


def reverse_search_matches_for_row(
    row: dict[str, Any],
    *,
    query: str,
    docs_by_eshidis: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    metadata_text = "\n".join(
        str(value or "")
        for value in [
            row.get("display_id"),
            row.get("source_label"),
            row.get("title"),
            row.get("authority_name") or row.get("authority"),
            row.get("region"),
            row.get("interest_reason"),
            row.get("budget_display"),
            row.get("deadline_display"),
            (row.get("ai_triage") or {}).get("reason") if isinstance(row.get("ai_triage"), dict) else None,
            row.get("row_text"),
        ]
    )
    if reverse_text_contains(metadata_text, query):
        matches.append(
            {
                "kind": "metadata",
                "label": "Στοιχεία έργου",
                "document_type": None,
                "snippet": reverse_search_snippet(metadata_text, query),
                "source_url": row.get("official_url"),
            }
        )
    for evidence in row.get("document_evidence") or []:
        if not isinstance(evidence, dict):
            continue
        evidence_text = "\n".join(
            [
                str(evidence.get("name") or ""),
                str(evidence.get("document_type") or ""),
                "\n".join(str(snippet or "") for snippet in evidence.get("snippets") or []),
            ]
        )
        if not reverse_text_contains(evidence_text, query):
            continue
        matches.append(
            {
                "kind": "document",
                "label": evidence.get("name") or "source document",
                "document_type": evidence.get("document_type"),
                "snippet": reverse_search_snippet(evidence_text, query),
                "source_url": evidence.get("document_url") or evidence.get("source_url"),
            }
        )
    eshidis_id = str(row.get("eshidis_id") or row.get("display_id") or "").strip()
    for document in docs_by_eshidis.get(eshidis_id, []):
        text = reverse_search_document_text(document)
        haystack = "\n".join(
            [
                str(getattr(document, "original_name", "") or ""),
                str(getattr(document, "document_type", "") or ""),
                text,
            ]
        )
        if not reverse_text_contains(haystack, query):
            continue
        matches.append(
            {
                "kind": "document",
                "label": getattr(document, "original_name", None) or "ESHIDIS document",
                "document_type": getattr(document, "document_type", None),
                "snippet": reverse_search_snippet(haystack, query),
                "source_url": None,
            }
        )
        if len(matches) >= MAX_REVERSE_DOCUMENT_MATCHES_PER_ROW:
            break
    return matches


def reverse_search_document_text(document: Any) -> str:
    text_path = str(getattr(document, "text_path", "") or "").strip()
    path = Path(text_path) if text_path and Path(text_path).is_absolute() else normalize_local_path(text_path)
    if path and path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:MAX_REVERSE_TEXT_READ_CHARS]
        except OSError:
            pass
    return str(getattr(document, "text_sample", "") or "")[:MAX_REVERSE_TEXT_READ_CHARS]


def reverse_text_contains(text: str, query: str) -> bool:
    normalized_text = normalize_greek(text)
    normalized_query = normalize_greek(query)
    if not normalized_query:
        return False
    return normalized_query in normalized_text


def reverse_search_snippet(text: str, query: str, *, radius: int = 190) -> str:
    normalized_text = normalize_greek(text)
    normalized_query = normalize_greek(query)
    index = normalized_text.find(normalized_query)
    if index < 0:
        return short_text_sample(text, limit=420) or ""
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    return compact_document_snippet(text[start:end])[:520]


def dashboard_scope(scope: str | None) -> str:
    return "focus"


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
    generated_at = payload.get("generated_at")
    triage: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("row_key") or "")
        ai = row.get("ai")
        if row_key and isinstance(ai, dict):
            triage[row_key] = {**ai, "triage_generated_at": generated_at}
    return triage


def row_key_for_tender(row: dict[str, Any]) -> str:
    return str(row.get("row_key") or row.get("eshidis_id") or row.get("display_id") or "")


def triage_overrides_by_key(user_email: str | None = None) -> dict[str, dict[str, object]]:
    try:
        overrides = db_triage_overrides_by_key(runtime_db_path())
        normalized_email = (user_email or "").strip().lower()
        if normalized_email:
            overrides = {**overrides, **db_user_triage_overrides_by_key(runtime_db_path(), user_email=normalized_email)}
        return overrides
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
            "triage_generated_at": ai.get("triage_generated_at"),
        },
        "ai_triage_hidden": not keep,
        "triage_override": override,
    }


def ignored_tenders_path() -> Path:
    return REPO_ROOT / "work/derived/ignored_tenders.json"


def ignored_tender_keys(user_email: str | None = None) -> set[str]:
    keys = set()
    normalized_email = (user_email or "").strip().lower()
    if normalized_email:
        try:
            keys.update(ignored_user_tender_keys(runtime_db_path(), user_email=normalized_email))
        except (OSError, sqlite3.Error):
            pass
        return {key for key in keys if key}
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


def dismiss_tender(row_key: str, *, user_email: str) -> dict[str, Any]:
    normalized_email = user_email.strip().lower()
    if not normalized_email:
        raise ValueError("User email is required.")
    row = next((item for item in merged_tender_rows() if row_key_for_tender(item) == row_key), {})
    dismiss_user_tender(
        runtime_db_path(),
        user_email=normalized_email,
        row_key=row_key,
        display_id=str(row.get("display_id") or row.get("official_id") or row.get("eshidis_id") or "") or None,
        source_label=str(row.get("source_label") or row.get("source") or "") or None,
        title=str(row.get("title") or "") or None,
        reason="Δεν με ενδιαφέρει",
        metadata={"source": "front_page"},
    )
    invalidate_ui_payload_cache()
    ignored = ignored_tender_keys(user_email=normalized_email)
    return {
        "ok": True,
        "row_key": row_key,
        "user_email": normalized_email,
        "ignored": len(ignored),
        "dashboard": dashboard_payload(scope="focus", user_email=normalized_email),
    }


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


def restore_admin_row(*, row_key: str, reason: str | None = None, user_email: str | None = None) -> dict[str, Any]:
    return admin_review_feedback(row_key=row_key, action="FORCE_KEEP", reason=reason, actor_email=user_email, user_email=user_email)


def admin_review_feedback(
    *,
    row_key: str,
    action: str,
    reason: str | None = None,
    actor_email: str | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    if action not in {"CONFIRM_DROP", "FORCE_KEEP"}:
        raise ValueError("Invalid admin review feedback action.")
    if action == "FORCE_KEEP":
        if user_email:
            remove_user_tender_dismissal(runtime_db_path(), row_key=row_key, user_email=user_email)
        else:
            remove_tender_dismissal(runtime_db_path(), row_key=row_key)
            remove_user_tender_dismissal(runtime_db_path(), row_key=row_key)
            remove_legacy_ignored_tender(row_key)
    metadata = {"source": "admin_panel", "actor_email": actor_email or ""}
    if user_email:
        upsert_user_triage_override(
            runtime_db_path(),
            user_email=user_email,
            row_key=row_key,
            action=action,
            reason=reason,
            metadata=metadata,
        )
    else:
        upsert_triage_override(
            runtime_db_path(),
            row_key=row_key,
            action=action,
            reason=reason,
            metadata=metadata,
        )
    invalidate_ui_payload_cache()
    return {
        "ok": True,
        "row_key": row_key,
        "action": action,
        "user_email": (user_email or "").strip().lower() or None,
        "dashboard": dashboard_payload(scope="focus", user_email=user_email),
        "admin": admin_audit_payload(user_email=user_email),
    }


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


def normalize_admin_user_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ADMIN_USER_ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ADMIN_USER_ROLES)}.")
    return normalized


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


def request_password_reset(payload: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    email = str(payload.get("email") or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Valid email is required.")
    user = get_admin_user(runtime_db_path(), email)
    if user and user.enabled:
        token, link = create_password_setup_invite(
            email=email,
            role=user.role,
            created_by="password-reset",
            base_url=base_url,
        )
        send_password_setup_email(email, link, role=user.role)
        return {"ok": True, "sent": True, "token_preview": token[:6]}
    return {"ok": True, "sent": True}


def invite_admin_user(payload: dict[str, Any], *, inviter: str | None, base_url: str) -> dict[str, Any]:
    email = str(payload.get("email") or "").strip().lower()
    role = normalize_admin_user_role(str(payload.get("role") or "user"))
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("Valid email is required.")
    token, link = create_password_setup_invite(email=email, role=role, created_by=inviter, base_url=base_url)
    send_password_setup_email(email, link, role=role)
    return {"ok": True, "sent": True, "email": email, "role": role, "token_preview": token[:6], "users": admin_users_payload()["users"]}


def admin_user_for_identifier(identifier: str):
    value = identifier.strip().lower().lstrip("#")
    if not value:
        raise ValueError("Email or user id is required.")
    if value.isdigit():
        user = get_admin_user_by_id(runtime_db_path(), int(value))
    else:
        user = get_admin_user(runtime_db_path(), value)
    if not user:
        raise ValueError("User was not found.")
    return user


def update_admin_user_role(payload: dict[str, Any], *, actor_email: str | None) -> dict[str, Any]:
    identifier = str(payload.get("identifier") or "").strip()
    role = normalize_admin_user_role(str(payload.get("role") or "user"))
    user = admin_user_for_identifier(identifier)
    actor = (actor_email or "").strip().lower()
    if user.email == actor and user.role == "admin" and role != "admin":
        raise ValueError("You cannot remove your own admin role.")
    if user.role == "admin" and role != "admin" and count_enabled_admin_users(runtime_db_path()) <= 1:
        raise ValueError("Cannot remove the last enabled admin.")
    updated = upsert_admin_user(runtime_db_path(), email=user.email, role=role, enabled=user.enabled)
    return {"ok": True, "user": {"id": updated.id, "email": updated.email, "role": updated.role}, "users": admin_users_payload()["users"]}


def create_password_setup_invite(*, email: str, role: str, created_by: str | None, base_url: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hash_reset_token(token)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_SETUP_TOKEN_TTL_MINUTES)).isoformat()
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
    role_label = {"admin": "διαχειριστής", "pricing": "τιμολόγηση", "tester": "δοκιμαστής"}.get(role, "χρήστης")
    text_body = (
        "Έχεις πρόσκληση στο Tender Radar.\n\n"
        f"Ρόλος: {role_label}\n"
        f"Όρισε password από εδώ: {link}\n\n"
        f"Το link ισχύει για {PASSWORD_SETUP_TOKEN_TTL_MINUTES} λεπτά και μπορεί να χρησιμοποιηθεί μία φορά."
    )
    html_body = (
        "<p>Έχεις πρόσκληση στο <strong>Tender Radar</strong>.</p>"
        f"<p>Ρόλος: <strong>{role_label}</strong></p>"
        f"<p><a href=\"{link}\">Ορισμός password</a></p>"
        f"<p>Το link ισχύει για {PASSWORD_SETUP_TOKEN_TTL_MINUTES} λεπτά και μπορεί να χρησιμοποιηθεί μία φορά.</p>"
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
                "id": user.id,
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


def admin_audit_payload(
    *,
    user_email: str | None = None,
    include_hidden_rows: bool = True,
    include_review_queue: bool = True,
) -> dict[str, Any]:
    overrides = triage_overrides_by_key(user_email=user_email)
    force_keep_keys = {key for key, item in overrides.items() if item.get("action") == "FORCE_KEEP"}
    ignored_keys = ignored_tender_keys() - force_keep_keys
    triage = ai_triage_by_row_key()
    rows = [attach_ai_triage(row, triage, overrides=overrides) for row in merged_tender_rows()]
    rows = rows_with_document_evidence(rows)
    row_by_key = {row_key_for_tender(row): row for row in rows if row_key_for_tender(row)}

    dismissed_rows = []
    for item in list_tender_dismissals(runtime_db_path()):
        row_key = str(item.get("row_key") or "")
        if row_key in force_keep_keys:
            continue
        row = row_by_key.get(row_key, {})
        if row:
            row = {**row, "ignored_at": item.get("ignored_at")}
        dismissed_rows.append(
            admin_hidden_row(
                row or item,
                category="DISMISSED",
                reason=str(item.get("reason") or "Χειροκίνητη επιλογή: Δεν με ενδιαφέρει"),
                restorable=True,
            )
        )
    for item in list_user_tender_dismissals(runtime_db_path()):
        row_key = str(item.get("row_key") or "")
        if row_key in force_keep_keys:
            continue
        row = row_by_key.get(row_key, {})
        if row:
            row = {**row, "ignored_at": item.get("ignored_at")}
        user_email = str(item.get("user_email") or "")
        dismissed_rows.append(
            admin_hidden_row(
                row or item,
                category="DISMISSED",
                reason=f"Χρήστης {user_email}: {item.get('reason') or 'Δεν με ενδιαφέρει'}",
                restorable=True,
            )
        )

    triage_hidden_rows = [
        admin_hidden_row(
            row,
            category=admin_ai_hidden_category(row),
            reason=admin_ai_hidden_reason(row),
            restorable=True,
        )
        for row in rows
        if row_key_for_tender(row) not in ignored_keys and row.get("ai_triage_hidden")
    ]

    active_source_rows = [row for row in rows if row_key_for_tender(row) not in ignored_keys]
    canonical_rows, duplicate_rows = suppress_linked_eshidis_duplicates(active_source_rows)
    official_deadlines = official_eshidis_deadlines_by_id(canonical_rows)
    dashboard_candidate_rows = [
        row
        for row in canonical_rows
        if row.get("interest_match") and not row.get("ai_triage_hidden")
    ]
    inactive_rows = [
        row
        for row in dashboard_candidate_rows
        if not dashboard_row_is_active(row, official_deadlines=official_deadlines)
    ]
    duplicate_hidden_rows = [
        admin_hidden_row(
            row,
            category="DUPLICATE",
            reason=str(row.get("duplicate_reason") or "Κρύφτηκε επειδή υπάρχει canonical ΕΣΗΔΗΣ εγγραφή."),
            restorable=False,
        )
        for row in duplicate_rows
    ]
    official_eshidis_rows = [row for row in canonical_rows if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ"]
    expired_hidden_rows = []
    missing_deadline_rows = []
    duplicate_candidate_rows = []
    for row in inactive_rows:
        raw_deadline = row.get("current_deadline_at") or row.get("submission_deadline") or (row.get("deadline_evidence") or {}).get("deadline_at")
        if raw_deadline and deadline_date(str(raw_deadline)):
            expired_hidden_rows.append(
                admin_hidden_row(
                    row,
                    category="EXPIRED",
                    reason=f"Κρύφτηκε επειδή η προθεσμία υποβολής ({deadline_display(str(raw_deadline))}) έχει λήξει.",
                    restorable=False,
                )
            )
        else:
            document_count = int(row.get("document_evidence_count") or 0)
            duplicate_candidate = best_possible_eshidis_duplicate(row, official_eshidis_rows)
            if duplicate_candidate:
                duplicate_candidate_rows.append(
                    admin_hidden_row(
                        row,
                        category="DUPLICATE_CANDIDATE",
                        reason=possible_duplicate_reason(row, duplicate_candidate, document_count=document_count),
                        restorable=False,
                        audit_match=duplicate_candidate,
                    )
                )
                continue
            obvious_drop_reason = obvious_out_of_scope_supply_service_reason(row)
            if obvious_drop_reason:
                missing_deadline_rows.append(
                    admin_hidden_row(
                        row,
                        category="OUT_OF_SCOPE_SUPPLY_SERVICE",
                        reason=obvious_drop_reason,
                        restorable=False,
                    )
                )
                continue
            missing_deadline_rows.append(
                admin_hidden_row(
                    row,
                    category="NO_DEADLINE_EVIDENCE",
                    reason=missing_deadline_reason(row, document_count=document_count),
                    restorable=False,
                )
            )
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
    hidden_rows = dismissed_rows + triage_hidden_rows + duplicate_hidden_rows + duplicate_candidate_rows + expired_hidden_rows + missing_deadline_rows
    hidden_rows = stamp_admin_hidden_events(hidden_rows)
    hidden_rows = sorted(hidden_rows, key=admin_hidden_row_sort_key, reverse=True)
    review_queue = admin_false_negative_review_queue(hidden_rows)
    payload = {
        "ok": True,
        "authenticated": True,
        "summary": {
            "audit_enrichment_version": "2026-07-19-deadline-v2",
            "hidden_total": len(hidden_rows),
            "dismissed": len(dismissed_rows),
            "ai_hidden": len(triage_hidden_rows),
            "duplicates": len(duplicate_hidden_rows),
            "duplicate_candidates": len(duplicate_candidate_rows),
            "expired": len(expired_hidden_rows),
            "missing_deadline": len(missing_deadline_rows),
            "source_errors": len(errors),
            "manual_force_keep": len(force_keep_keys),
            "review_queue_total": len(review_queue),
            "review_queue_high": sum(1 for row in review_queue if row.get("review_priority") == "HIGH"),
            "review_queue_medium": sum(1 for row in review_queue if row.get("review_priority") == "MEDIUM"),
            "review_queue_low": sum(1 for row in review_queue if row.get("review_priority") == "LOW"),
        },
        "source_errors": errors,
    }
    if include_hidden_rows:
        payload["hidden_rows"] = hidden_rows
    if include_review_queue:
        payload["review_queue"] = review_queue
    return payload


def admin_false_negative_review_queue(hidden_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = []
    for row in hidden_rows:
        review = admin_false_negative_review_metadata(row)
        if not review:
            continue
        queue.append({**row, **review})
    return sorted(queue, key=admin_review_row_sort_key, reverse=True)


def admin_false_negative_review_metadata(row: dict[str, Any]) -> dict[str, str] | None:
    override = row.get("triage_override") if isinstance(row.get("triage_override"), dict) else {}
    if override.get("action") == "CONFIRM_DROP":
        return None
    category = str(row.get("category") or "")
    ai_decision = str(row.get("ai_decision") or "")
    confidence = _float_or_none(row.get("ai_confidence"))
    title = normalize_greek(str(row.get("title") or ""))
    reason = normalize_greek(str(row.get("reason") or ""))
    combined = f"{title} {reason}"
    public_signal = any(
        term in combined
        for term in (
            "εργο",
            "εργασι",
            "οδικ",
            "οδοποι",
            "συντηρη",
            "ασφαλτο",
            "κατασκευ",
            "επισκευ",
            "αποκαταστα",
            "διαγωνισ",
            "διακηρυ",
            "προυπολογισ",
        )
    )
    tender_signal = any(term in title for term in ("διαγωνισ", "διακηρυ", "υποβολη", "προσφορ", "προθεσμι"))
    if category == "OUT_OF_SCOPE_SUPPLY_SERVICE":
        return None
    if category == "NO_DEADLINE_EVIDENCE":
        if obvious_out_of_scope_supply_service_reason(row):
            return None
        return {
            "review_priority": "HIGH" if tender_signal else "MEDIUM",
            "review_reason": "Υπάρχει ενδιαφέρον έργου/περιοχής αλλά δεν τεκμηριώθηκε ενεργή προθεσμία.",
        }
    if category == "DUPLICATE_CANDIDATE":
        return {
            "review_priority": "MEDIUM",
            "review_reason": "Πιθανό διπλότυπο ΕΣΗΔΗΣ. Θέλει έλεγχο πριν θεωρηθεί ασφαλές κόψιμο.",
        }
    if category.startswith("AI_DROP"):
        if confidence is None or confidence < 0.9:
            return {
                "review_priority": "HIGH",
                "review_reason": "AI απόρριψη με μη υψηλή βεβαιότητα.",
            }
        if public_signal and ai_decision in {"DROP_OUT_OF_SCOPE_SUPPLY_SERVICE", "DROP_NOT_PUBLIC_WORKS"}:
            if obvious_out_of_scope_supply_service_reason(row):
                return None
            return {
                "review_priority": "HIGH",
                "review_reason": "AI απόρριψη αλλά υπάρχουν λέξεις δημοσίων έργων που μπορεί να δείχνουν false negative.",
            }
        if category in {"AI_DROP_SUPPLY_SERVICE", "AI_DROP_NOT_PUBLIC_WORKS"}:
            return {
                "review_priority": "MEDIUM",
                "review_reason": "AI απόρριψη εκτός αντικειμένου. Δειγματοληπτικός έλεγχος για false negatives.",
            }
        return {
            "review_priority": "LOW",
            "review_reason": "AI απόρριψη χαμηλότερου κινδύνου, κρατιέται για περιοδικό audit.",
        }
    return None


def obvious_out_of_scope_supply_service_reason(row: dict[str, Any]) -> str | None:
    text = normalize_greek(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "title",
                "display_id",
            )
        )
    )
    if should_keep_obvious_road_maintenance_review(row, normalized_text=text):
        return None
    categories = (
        (
            "προμήθεια καυσίμων/λιπαντικών, όχι δημόσιο έργο κατασκευής",
            ("καυσιμ", "λιπαντικ"),
        ),
        (
            "μεταφορά μαθητών, δηλαδή υπηρεσία μεταφοράς εκτός δημοσίων έργων",
            ("μεταφορα μαθητ", "μεταφορασ μαθητ"),
        ),
        (
            "προμήθεια/εγκατάσταση συστήματος τηλεελέγχου ή τηλεχειρισμού, όχι κατασκευαστικό δημόσιο έργο",
            ("τηλεελεγχ", "τηλεχειρισ", "συστημα τηλε", "συστηματος τηλε"),
        ),
    )
    for label, terms in categories:
        if any(term in text for term in terms):
            return f"Κρύφτηκε επειδή ο τίτλος δείχνει καθαρά {label}."
    return None


def should_keep_obvious_road_maintenance_review(row: dict[str, Any], *, normalized_text: str | None = None) -> bool:
    text = normalized_text or normalize_greek(str(row.get("title") or ""))
    road_terms = ("οδικου δικτυου", "οδικο δικτυο", "επαρχιακου δικτυου", "επαρχιακο δικτυο", "οδοποι", "οδων")
    maintenance_terms = ("συντηρη", "επισκευ", "αποκαταστα", "βελτιω", "αποχιον", "χιονο")
    tender_terms = ("διαγωνισ", "διακηρυ", "προσφορ", "αναδοχ")
    return any(term in text for term in road_terms) and any(term in text for term in maintenance_terms) and any(
        term in text for term in tender_terms
    )


def admin_review_row_sort_key(row: dict[str, Any]) -> tuple[int, bool, str, str, str]:
    priority_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(str(row.get("review_priority") or ""), 0)
    audit_at = str(row.get("audit_at") or "").strip()
    return (
        priority_rank,
        bool(audit_at),
        deadline_sort_key(audit_at),
        str(row.get("display_id") or ""),
        str(row.get("row_key") or ""),
    )


def admin_hidden_event_at(row: dict[str, Any]) -> str:
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    override = row.get("triage_override") if isinstance(row.get("triage_override"), dict) else {}
    for value in (
        row.get("ignored_at"),
        override.get("created_at"),
        ai.get("triage_generated_at"),
        row.get("audit_first_seen_at"),
    ):
        text = admin_audit_timestamp_text(value)
        if text:
            return text
    return ""


def admin_audit_timestamp_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or text == "9999":
        return ""
    if re.fullmatch(r"\d{13}", text):
        try:
            return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return ""
    if re.fullmatch(r"\d{10}", text):
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return ""
    return text


def stamp_admin_hidden_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = utc_now_iso()
    try:
        existing = admin_hidden_events_by_key(runtime_db_path())
    except (OSError, sqlite3.Error):
        existing = {}
    stamped: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get("row_key") or "")
        category = str(row.get("category") or "")
        event = existing.get((row_key, category), {})
        existing_first_seen = admin_audit_timestamp_text(event.get("first_seen_at"))
        preferred = admin_audit_timestamp_text(row.get("audit_at"))
        audit_at = preferred or existing_first_seen or now
        if row_key and category:
            try:
                upsert_admin_hidden_event(
                    runtime_db_path(),
                    row_key=row_key,
                    category=category,
                    first_seen_at=audit_at,
                    last_seen_at=now,
                )
            except (OSError, sqlite3.Error):
                pass
        stamped.append({**row, "audit_at": audit_at})
    return stamped


def admin_hidden_row_sort_key(row: dict[str, Any]) -> tuple[bool, str, str, str]:
    audit_at = str(row.get("audit_at") or "").strip()
    return (
        bool(audit_at),
        deadline_sort_key(audit_at),
        str(row.get("display_id") or ""),
        str(row.get("row_key") or ""),
    )


def admin_ai_hidden_category(row: dict[str, Any]) -> str:
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    return {
        "DROP_ADMIN": "AI_DROP_ADMIN",
        "DROP_OUT_OF_SCOPE_SUPPLY_SERVICE": "AI_DROP_SUPPLY_SERVICE",
        "DROP_NOT_PUBLIC_WORKS": "AI_DROP_NOT_PUBLIC_WORKS",
        "EARLY_SIGNAL": "AI_EARLY_SIGNAL",
    }.get(str(ai.get("decision") or ""), "AI_HIDDEN")


def admin_ai_hidden_reason(row: dict[str, Any]) -> str:
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    decision = str(ai.get("decision") or "")
    label = {
        "DROP_ADMIN": "διοικητική/μη διαγωνιστική πράξη",
        "DROP_OUT_OF_SCOPE_SUPPLY_SERVICE": "προμήθεια ή υπηρεσία εκτός δημοσίων έργων",
        "DROP_NOT_PUBLIC_WORKS": "όχι δημόσιο έργο κατασκευής",
        "EARLY_SIGNAL": "πρώιμο σήμα, όχι ενεργός διαγωνισμός",
    }.get(decision, "μη κατάλληλο για την καθημερινή λίστα")
    reason = str(ai.get("reason") or "").strip()
    if reason:
        return f"AI έλεγχος: {label}. {reason}"
    return f"AI έλεγχος: {label}."


def admin_hidden_row(
    row: dict[str, Any],
    *,
    category: str,
    reason: str,
    restorable: bool,
    audit_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row_key = row_key_for_tender(row) or str(row.get("row_key") or "")
    ai = row.get("ai_triage") if isinstance(row.get("ai_triage"), dict) else {}
    override = row.get("triage_override") if isinstance(row.get("triage_override"), dict) else {}
    audit_at = admin_hidden_event_at(row)
    return {
        "row_key": row_key,
        "category": category,
        "restorable": restorable,
        "audit_at": audit_at,
        "display_id": row.get("display_id") or row.get("eshidis_id") or row.get("official_id") or "",
        "source_label": row.get("source_label") or "",
        "title": row.get("title") or "",
        "authority_name": row.get("authority_name") or row.get("authority") or "",
        "deadline_display": row.get("deadline_display") or row.get("current_deadline_at") or "",
        "official_url": row.get("official_url") or row.get("source_url") or row.get("attachment_url") or "",
        "reason": reason,
        "ai_decision": ai.get("decision"),
        "ai_confidence": ai.get("confidence"),
        "ai_confidence_band": ai_confidence_band_for_row({**row, "ai_triage": ai, "ai_triage_hidden": True}),
        "profile_fit": profile_fit_for_row(row),
        "triage_override": override,
        "feedback_action": override.get("action"),
        "feedback_reason": override.get("reason"),
        "audit_match": audit_match,
    }


def best_possible_eshidis_duplicate(row: dict[str, Any], official_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if str(row.get("source_label") or "") == "ΕΣΗΔΗΣ":
        return None
    candidates: list[dict[str, Any]] = []
    for official in official_rows:
        score, signals = possible_eshidis_duplicate_score(row, official)
        if score < 0.72:
            continue
        eshidis_id = str(official.get("eshidis_id") or official.get("display_id") or "")
        candidates.append(
            {
                "eshidis_id": eshidis_id,
                "title": official.get("title") or "",
                "authority_name": official.get("authority_name") or official.get("authority") or "",
                "deadline": official.get("current_deadline_at") or official.get("submission_deadline") or "",
                "official_url": (official.get("official_url") or official_resource_url(eshidis_id)) if eshidis_id else "",
                "score": round(score, 3),
                "signals": signals,
            }
        )
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (float(item.get("score") or 0), str(item.get("deadline") or "")), reverse=True)[0]


def possible_eshidis_duplicate_score(row: dict[str, Any], official: dict[str, Any]) -> tuple[float, list[str]]:
    signals: list[str] = []
    row_title_tokens = title_match_tokens(row.get("title"))
    official_title_tokens = title_match_tokens(official.get("title"))
    title_score = token_overlap_score(row_title_tokens, official_title_tokens)
    if title_score >= 0.45:
        signals.append(f"title_overlap {title_score:.2f}")
    row_authority = normalized_duplicate_text(row.get("authority_name") or row.get("authority"))
    official_authority = normalized_duplicate_text(official.get("authority_name") or official.get("authority"))
    authority_match = bool(row_authority and official_authority and (row_authority in official_authority or official_authority in row_authority))
    authority_token_score = token_overlap_score(title_match_tokens(row_authority), title_match_tokens(official_authority))
    if authority_token_score >= 0.5:
        authority_match = True
    if authority_match:
        signals.append("authority_match")
    row_interest = normalized_duplicate_text(row.get("interest_reason"))
    location_match = bool(row_interest and official_authority and any(part and part in official_authority for part in re.split(r"[,/]", row_interest)))
    if location_match:
        signals.append("location_match")
    linked_match = str(official.get("eshidis_id") or official.get("display_id") or "") in set(linked_eshidis_ids_for_row(row))
    if linked_match:
        signals.append("explicit_linked_eshidis")
    score = title_score * 0.62
    if authority_match:
        score += 0.28
    if location_match:
        score += 0.12
    if linked_match:
        score += 0.5
    return min(score, 1.0), signals


def title_match_tokens(value: object) -> set[str]:
    normalized = normalized_duplicate_text(value)
    stop_words = {
        "και",
        "της",
        "του",
        "των",
        "στη",
        "στο",
        "στις",
        "στον",
        "για",
        "εργο",
        "εργου",
        "εργων",
        "δημοσ",
        "δημου",
        "διακηρυξη",
        "ανοιχτου",
        "ηλεκτρονικου",
        "διαγωνισμου",
        "δρασεισ",
    }
    return {token for token in re.findall(r"[a-zα-ω0-9]+", normalized) if len(token) >= 4 and token not in stop_words}


def token_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, min(len(left), len(right)))


def possible_duplicate_reason(row: dict[str, Any], match: dict[str, Any], *, document_count: int) -> str:
    return (
        f"Κρύφτηκε από την αρχική επειδή δεν τεκμηριώθηκε ξεχωριστή ενεργή προθεσμία, "
        f"αλλά το audit το συσχέτισε ως πιθανή διπλοεγγραφή του επίσημου ΕΣΗΔΗΣ {match.get('eshidis_id')} "
        f"({match.get('title')}) με λήξη {deadline_display(str(match.get('deadline') or '')) or match.get('deadline') or 'UNKNOWN'}. "
        f"Σήματα: {', '.join(match.get('signals') or []) or 'UNKNOWN'}. "
        f"Fetched/OCR έγγραφα που ελέγχθηκαν: {document_count}."
    )


def missing_deadline_reason(row: dict[str, Any], *, document_count: int) -> str:
    source_label = str(row.get("source_label") or row.get("source") or "πηγή")
    if document_count > 0:
        return (
            f"Κρύφτηκε από την αρχική επειδή στα {document_count} κατεβασμένα/OCR έγγραφα της πηγής {source_label} "
            "δεν τεκμηριώθηκε ενεργή καταληκτική ημερομηνία υποβολής προσφορών και δεν βρέθηκε ισχυρή σύνδεση "
            "με επίσημη εγγραφή ΕΣΗΔΗΣ."
        )
    return (
        f"Κρύφτηκε από την αρχική επειδή η πηγή {source_label} δεν έδωσε επαρκή έγγραφα ή κείμενο για να τεκμηριωθεί "
        "ενεργή καταληκτική ημερομηνία υποβολής προσφορών και δεν βρέθηκε ισχυρή σύνδεση με επίσημη εγγραφή ΕΣΗΔΗΣ."
    )


def discovery_history_path() -> Path:
    return REPO_ROOT / "work/derived/discovery_runs.json"


def latest_discovery_run_payload() -> dict[str, Any] | None:
    return latest_discovery_run(discovery_history_path())


def location_focus_profile() -> dict[str, Any]:
    path = REPO_ROOT / "config" / "locations.yml"
    data = cached_data(("locations", str(path), path_mtime_ns(path)), lambda: load_config(path) if path.exists() else {})
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
    payload = cached_data(("expanded_report", str(path), path_mtime_ns(path)), lambda: json.loads(path.read_text(encoding="utf-8")))
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
    authority_documents = authority_documents_by_key()
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
        authority_docs = authority_documents.get(row_key, [])
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
    return cached_data(("authority_documents", str(path), path_mtime_ns(path)), lambda: json.loads(path.read_text(encoding="utf-8")))


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
    payload = cached_data(("kimdis_documents", str(path), path_mtime_ns(path)), lambda: json.loads(path.read_text(encoding="utf-8")))
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
    return cached_data(("sqlite_tender_rows", str(db_path), path_mtime_ns(db_path)), lambda: read_sqlite_tender_rows(db_path))


def read_sqlite_tender_rows(db_path: Path) -> list[dict[str, Any]]:
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


def linked_eshidis_preview_documents(eshidis_ids: list[str]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for eshidis_id in list(dict.fromkeys(str(value).strip() for value in eshidis_ids if str(value).strip())):
        for document in document_preview_payload(eshidis_id).get("documents") or []:
            if not isinstance(document, dict):
                continue
            documents.append(
                {
                    **document,
                    "eshidis_id": eshidis_id,
                    "label": f"ΕΣΗΔΗΣ {eshidis_id} · {document.get('label') or 'Αρχείο'}",
                }
            )
    return documents


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
    linked_eshidis_documents = linked_eshidis_preview_documents(linked_eshidis_ids)
    linked_eshidis_file_count = len(linked_eshidis_documents)
    return {
        "official_id": official_id,
        "source_label": "ΚΗΜΔΗΣ",
        "official_url": document.get("attachment_url") or document.get("source_url"),
        "candidate_status": document.get("candidate_status"),
        "verification_status": document.get("verification_status"),
        "linked_eshidis_ids": linked_eshidis_ids,
        "linked_eshidis_file_count": linked_eshidis_file_count,
        "linked_eshidis_documents": linked_eshidis_documents,
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
    linked_eshidis_documents = linked_eshidis_preview_documents(linked_eshidis_ids)
    linked_eshidis_file_count = len(linked_eshidis_documents)
    return {
        "row_key": row_key,
        "source_label": "Φορέας",
        "official_url": row.get("official_url") or row.get("attachment_url"),
        "candidate_status": row.get("status"),
        "official_status": "LINKED_TO_ESHIDIS" if linked_eshidis_ids else "NO_ESHIDIS_ID_FOUND",
        "linked_eshidis_ids": linked_eshidis_ids,
        "linked_eshidis_file_count": linked_eshidis_file_count,
        "linked_eshidis_documents": linked_eshidis_documents,
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
    as_of: date | datetime | None = None,
    official_deadlines: dict[str, str] | None = None,
) -> bool:
    raw_deadline = raw_dashboard_deadline(row, official_deadlines=official_deadlines)
    deadline = deadline_datetime(raw_deadline)
    if deadline is None:
        return False
    if isinstance(as_of, datetime):
        current = as_of if as_of.tzinfo else as_of.replace(tzinfo=dashboard_timezone())
        return deadline >= current.astimezone(deadline.tzinfo)
    if isinstance(as_of, date):
        return deadline.date() >= as_of
    return deadline >= datetime.now(dashboard_timezone())


def raw_dashboard_deadline(row: dict[str, Any], *, official_deadlines: dict[str, str] | None = None) -> str:
    raw_deadline = str(row.get("current_deadline_at") or row.get("submission_deadline") or "")
    if not raw_deadline and official_deadlines:
        linked_deadlines = [
            official_deadlines[eshidis_id]
            for eshidis_id in linked_eshidis_ids_for_row(row)
            if eshidis_id in official_deadlines
        ]
        if linked_deadlines:
            raw_deadline = max(linked_deadlines, key=deadline_sort_key)
    if not raw_deadline:
        raw_deadline = str((row.get("deadline_evidence") or {}).get("deadline_at") or "")
    return raw_deadline


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


def empty_expired_cleanup_report() -> dict[str, Any]:
    return {
        "ok": True,
        "summary": {
            "expired_rows_checked": 0,
            "files_deleted": 0,
            "bytes_deleted": 0,
            "attachments_cleared": 0,
            "source_documents_cleared": 0,
            "legacy_documents_cleared": 0,
            "errors": 0,
        },
        "rows": [],
        "errors": [],
    }


def cleanup_expired_public_work_downloads(
    rows: list[dict[str, Any]],
    *,
    as_of: date | datetime | None = None,
    official_deadlines: dict[str, str] | None = None,
) -> dict[str, Any]:
    db_path = runtime_db_path()
    report: dict[str, Any] = {
        "ok": True,
        "summary": {
            "expired_rows_checked": 0,
            "files_deleted": 0,
            "bytes_deleted": 0,
            "attachments_cleared": 0,
            "source_documents_cleared": 0,
            "legacy_documents_cleared": 0,
            "errors": 0,
        },
        "rows": [],
        "errors": [],
    }
    expired_rows = []
    for row in rows:
        if not row_key_for_tender(row):
            continue
        raw_deadline = raw_dashboard_deadline(row, official_deadlines=official_deadlines)
        if deadline_datetime(raw_deadline) is None:
            continue
        if not dashboard_row_is_active(row, as_of=as_of, official_deadlines=official_deadlines):
            expired_rows.append(row)
    report["summary"]["expired_rows_checked"] = len(expired_rows)
    if not expired_rows:
        return report
    deleted_paths: set[str] = set()
    for row in expired_rows:
        row_key = row_key_for_tender(row)
        row_report: dict[str, Any] = {"row_key": row_key, "display_id": row.get("display_id"), "files_deleted": 0}
        try:
            if str(row.get("eshidis_id") or "").strip().isdigit():
                cleared = cleanup_expired_eshidis_attachment_downloads(
                    db_path,
                    eshidis_id=str(row.get("eshidis_id") or "").strip(),
                    deleted_paths=deleted_paths,
                )
                row_report["attachments_cleared"] = cleared.get("records_cleared", 0)
                report["summary"]["attachments_cleared"] += int(cleared.get("records_cleared") or 0)
                report["summary"]["files_deleted"] += int(cleared.get("files_deleted") or 0)
                report["summary"]["bytes_deleted"] += int(cleared.get("bytes_deleted") or 0)
                row_report["files_deleted"] += int(cleared.get("files_deleted") or 0)
            cleared_source = cleanup_expired_source_document_downloads(
                db_path,
                row_key=row_key,
                deleted_paths=deleted_paths,
            )
            report["summary"]["source_documents_cleared"] += int(cleared_source.get("records_cleared") or 0)
            report["summary"]["files_deleted"] += int(cleared_source.get("files_deleted") or 0)
            report["summary"]["bytes_deleted"] += int(cleared_source.get("bytes_deleted") or 0)
            row_report["source_documents_cleared"] = cleared_source.get("records_cleared", 0)
            row_report["files_deleted"] += int(cleared_source.get("files_deleted") or 0)
            cleared_legacy = cleanup_expired_legacy_document_index_downloads(
                row_key=row_key,
                deleted_paths=deleted_paths,
            )
            report["summary"]["legacy_documents_cleared"] += int(cleared_legacy.get("records_cleared") or 0)
            report["summary"]["files_deleted"] += int(cleared_legacy.get("files_deleted") or 0)
            report["summary"]["bytes_deleted"] += int(cleared_legacy.get("bytes_deleted") or 0)
            row_report["legacy_documents_cleared"] = cleared_legacy.get("records_cleared", 0)
            row_report["files_deleted"] += int(cleared_legacy.get("files_deleted") or 0)
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            report["ok"] = False
            report["summary"]["errors"] += 1
            error = {"row_key": row_key, "error": str(exc)}
            report["errors"].append(error)
            row_report["error"] = str(exc)
        if any(row_report.get(key) for key in ("files_deleted", "attachments_cleared", "source_documents_cleared", "legacy_documents_cleared", "error")):
            report["rows"].append(row_report)
    return report


def cleanup_expired_eshidis_attachment_downloads(
    db_path: Path,
    *,
    eshidis_id: str,
    deleted_paths: set[str],
) -> dict[str, int]:
    if not db_path.exists():
        return {"records_cleared": 0, "files_deleted": 0, "bytes_deleted": 0}
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    records_cleared = files_deleted = bytes_deleted = 0
    try:
        rows = connection.execute(
            """
            SELECT attachments.id, attachments.local_path
            FROM attachments
            JOIN tenders ON tenders.id = attachments.tender_id
            WHERE tenders.eshidis_id = ?
              AND attachments.local_path IS NOT NULL
            """,
            (eshidis_id,),
        ).fetchall()
        for row in rows:
            deleted = delete_downloaded_file(_none_or_str(row["local_path"]), deleted_paths=deleted_paths)
            files_deleted += int(deleted.get("files_deleted") or 0)
            bytes_deleted += int(deleted.get("bytes_deleted") or 0)
            connection.execute(
                """
                UPDATE attachments
                SET local_path = NULL, size_bytes = NULL, sha256 = NULL
                WHERE id = ?
                """,
                (row["id"],),
            )
            records_cleared += 1
        connection.commit()
    finally:
        connection.close()
    return {"records_cleared": records_cleared, "files_deleted": files_deleted, "bytes_deleted": bytes_deleted}


def cleanup_expired_source_document_downloads(
    db_path: Path,
    *,
    row_key: str,
    deleted_paths: set[str],
) -> dict[str, int]:
    if not db_path.exists():
        return {"records_cleared": 0, "files_deleted": 0, "bytes_deleted": 0}
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    records_cleared = files_deleted = bytes_deleted = 0
    try:
        rows = connection.execute(
            """
            SELECT id, local_path
            FROM source_documents
            WHERE row_key = ?
              AND local_path IS NOT NULL
            """,
            (row_key,),
        ).fetchall()
        for row in rows:
            deleted = delete_downloaded_file(_none_or_str(row["local_path"]), deleted_paths=deleted_paths)
            files_deleted += int(deleted.get("files_deleted") or 0)
            bytes_deleted += int(deleted.get("bytes_deleted") or 0)
            connection.execute(
                """
                UPDATE source_documents
                SET local_path = NULL, size_bytes = NULL, sha256 = NULL
                WHERE id = ?
                """,
                (row["id"],),
            )
            records_cleared += 1
        connection.commit()
    finally:
        connection.close()
    return {"records_cleared": records_cleared, "files_deleted": files_deleted, "bytes_deleted": bytes_deleted}


def cleanup_expired_legacy_document_index_downloads(
    *,
    row_key: str,
    deleted_paths: set[str],
) -> dict[str, int]:
    if row_key.startswith("KIMDIS:"):
        official_id = row_key.split(":", 1)[1]
        return cleanup_legacy_index_documents(
            REPO_ROOT / "work/derived/kimdis_open_proc_documents.json",
            lambda document: str(document.get("official_id") or "") == official_id,
            deleted_paths=deleted_paths,
        )
    return cleanup_legacy_index_documents(
        authority_document_index_path(),
        lambda document: str(document.get("row_key") or "") == row_key,
        deleted_paths=deleted_paths,
    )


def cleanup_legacy_index_documents(
    path: Path,
    matcher: Any,
    *,
    deleted_paths: set[str],
) -> dict[str, int]:
    if not path.exists():
        return {"records_cleared": 0, "files_deleted": 0, "bytes_deleted": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = payload.get("documents") if isinstance(payload.get("documents"), list) else []
    records_cleared = files_deleted = bytes_deleted = 0
    changed = False
    for document in documents:
        if not isinstance(document, dict) or not matcher(document) or not document.get("local_path"):
            continue
        deleted = delete_downloaded_file(_none_or_str(document.get("local_path")), deleted_paths=deleted_paths)
        files_deleted += int(deleted.get("files_deleted") or 0)
        bytes_deleted += int(deleted.get("bytes_deleted") or 0)
        for key in ("local_path", "size_bytes", "sha256"):
            document[key] = None
        records_cleared += 1
        changed = True
    if changed:
        payload["updated_at"] = utc_now_iso()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"records_cleared": records_cleared, "files_deleted": files_deleted, "bytes_deleted": bytes_deleted}


def delete_downloaded_file(value: str | None, *, deleted_paths: set[str]) -> dict[str, int]:
    path = normalize_local_path(value)
    if path is None:
        return {"files_deleted": 0, "bytes_deleted": 0}
    key = str(path)
    if key in deleted_paths:
        return {"files_deleted": 0, "bytes_deleted": 0}
    size = path.stat().st_size
    path.unlink()
    deleted_paths.add(key)
    prune_empty_download_dirs(path.parent)
    return {"files_deleted": 1, "bytes_deleted": size}


def prune_empty_download_dirs(path: Path) -> None:
    work_dir = (REPO_ROOT / "work").resolve()
    current = path.resolve()
    while current != work_dir and work_dir in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def deadline_date(value: str) -> date | None:
    sort_key = deadline_sort_key(value)
    if sort_key == "9999":
        return None
    try:
        return date.fromisoformat(sort_key[:10])
    except ValueError:
        return None


def deadline_datetime(value: str) -> datetime | None:
    sort_key = deadline_sort_key(value)
    if sort_key == "9999":
        return None
    local_tz = dashboard_timezone()
    date_part = sort_key[:10]
    rest = sort_key[10:].strip()
    if not rest:
        try:
            return datetime.combine(date.fromisoformat(date_part), datetime.max.time(), tzinfo=local_tz)
        except ValueError:
            return None
    candidate = f"{date_part} {rest}".replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(local_tz)


def dashboard_timezone() -> ZoneInfo:
    path = REPO_ROOT / "config" / "locations.yml"
    try:
        config = cached_data(("dashboard_timezone_config", str(path), path_mtime_ns(path)), lambda: load_config(path))
        name = str(config.get("timezone") or "Europe/Athens")
        return ZoneInfo(name)
    except (OSError, ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Athens")


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
      <button id="forgotPasswordBtn" class="textButton" type="button">Ξέχασα το password</button>
      <p id="loginStatus" class="noteText"></p>
    </div>
    <footer class="legalFooter">
      <details>
        <summary>Όροι χρήσης</summary>
        <p>Το Tender Radar οργανώνει δημόσια διαθέσιμες αναρτήσεις διαγωνισμών. Πριν από προσφορά ελέγχεις πάντα την επίσημη καρτέλα ΕΣΗΔΗΣ και τα τεύχη του φορέα.</p>
      </details>
      <details>
        <summary>Privacy</summary>
        <p>Αποθηκεύονται email, ρόλος, hash password, session cookie και προσωπικές επιλογές απόκρυψης. Δεν αποθηκεύονται plaintext passwords.</p>
      </details>
      <details>
        <summary>Οδηγίες</summary>
        <p>Η αρχική δείχνει ενεργά δημόσια έργα περιοχής. Τα κουμπιά ΕΣΗΔΗΣ, ZIP και Δεν με ενδιαφέρει ανοίγουν επίσημα στοιχεία, κατεβάζουν φάκελο ή κρύβουν έργο μόνο για τον δικό σου χρήστη.</p>
      </details>
    </footer>
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
      <button class="nav active" data-view="overview">Δημόσια<br>έργα</button>
      <button id="pricingNavBtn" class="nav" data-view="workflow">Αντίστροφη<br>αναζήτηση</button>
      <button class="nav" data-view="entalmata">Εντάλματα</button>
      <button id="adminNavBtn" class="nav" data-view="adminPanel">Admin<br>panel</button>
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
          <p class="mutedLine">Η αναζήτηση ελέγχει τις συνδεδεμένες πηγές και κρατά μόνο έργα με ενεργή προθεσμία.</p>
          <p id="discoverySafetyText" class="mutedLine">Δεν υπάρχει ακόμη ιστορικό τελευταίας αναζήτησης.</p>
        </div>
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

      <details class="interestProfileBox">
        <summary>Προσωπικό προφίλ ενδιαφέροντος</summary>
        <div class="interestProfileGrid">
          <label>Λέξεις που θέλω
            <textarea id="profileIncludeInput" rows="3" placeholder="οδοποιία&#10;ασφαλτόστρωση&#10;συντήρηση"></textarea>
          </label>
          <label>Λέξεις που κόβω
            <textarea id="profileExcludeInput" rows="3" placeholder="καύσιμα&#10;μεταφορά μαθητών"></textarea>
          </label>
          <label>Ελάχιστος προϋπολογισμός
            <input id="profileMinBudgetInput" type="number" min="0" step="1000" placeholder="π.χ. 50000">
          </label>
          <label>Μέγιστος προϋπολογισμός
            <input id="profileMaxBudgetInput" type="number" min="0" step="1000" placeholder="π.χ. 5000000">
          </label>
        </div>
        <fieldset class="profileCategoryBox">
          <legend>Κατηγορίες έργων που με ενδιαφέρουν</legend>
          <div id="profileCategoryOptions" class="profileCategoryOptions"></div>
          <p class="noteText">Αν δεν επιλέξεις κατηγορία, δεν μπαίνει περιορισμός κατηγορίας.</p>
        </fieldset>
        <div class="toolbar compact">
          <button id="saveInterestProfileBtn" class="secondary">Αποθήκευση προφίλ</button>
          <span id="interestProfileStatus" class="noteText">Χωρίς προσωπικούς περιορισμούς.</span>
        </div>
      </details>

      <div class="metrics">
        <div><span id="visibleTenderCount">0</span><small>έργα στη λίστα</small></div>
        <div><span id="focusTenderCount">0</span><small>ταιριάζουν στην περιοχή</small></div>
      </div>

      <section class="deadlineWatch">
        <div class="deadlineWatchHeader">
          <div>
            <p class="eyebrow">Λήγουν σύντομα</p>
            <h3>Καθημερινή εικόνα ενεργειών</h3>
          </div>
          <span id="deadlineWatchSummary" class="noteText">Υπολογίζεται από την τρέχουσα λίστα.</span>
        </div>
        <div id="deadlineWatchBuckets" class="deadlineBuckets"></div>
      </section>

      <details class="sourceAudit" open hidden>
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
                  <th>Health</th>
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
      <div class="searchPanel">
        <p class="eyebrow">ΑΝΤΙΣΤΡΟΦΗ ΑΝΑΖΗΤΗΣΗ</p>
        <h2>Βρες ενεργά έργα από λέξη ή φράση</h2>
        <p class="mutedLine">Πρώτα ενημέρωσε τη βάση από τα ενεργά ΕΣΗΔΗΣ. Μετά η αναζήτηση ψάχνει στα αποθηκευμένα τεύχη και άρθρα.</p>
        <div class="toolbar compact">
          <label>Ενεργό παράθυρο ΕΣΗΔΗΣ <input id="pricingDiscoveryLimit" type="number" min="1" max="500" value="500"></label>
          <label>Νέα έργα <input id="pricingMaxNewProjects" type="number" min="1" max="100" value="15"></label>
          <button id="pricingIngestActiveBtn">Ενημέρωση βάσης ΕΣΗΔΗΣ</button>
        </div>
        <p id="pricingIngestStatus" class="mutedLine">Δεν έχει ξεκινήσει ενημέρωση pricing σε αυτή τη συνεδρία.</p>
        <div class="reverseSearchForm">
          <label class="reverseSearchInputLabel">
            <span>Λέξη ή φράση</span>
            <input id="reverseSearchInput" type="search" placeholder="π.χ. οδοποιία, ασφαλτόστρωση, άρθρο 2.2">
          </label>
          <button id="reverseSearchBtn">Αναζήτηση</button>
        </div>
        <p id="reverseSearchStatus" class="mutedLine">Γράψε έναν όρο για να ξεκινήσεις.</p>
      </div>
      <div class="metrics">
        <div><span id="reverseMatchCount">0</span><small>έργα με match</small></div>
        <div><span id="reverseSearchedCount">0</span><small>ενεργά έργα ελέγχθηκαν</small></div>
      </div>
      <div id="reverseSearchResults" class="reverseResults">
        <div class="emptyState">Τα αποτελέσματα θα εμφανιστούν εδώ.</div>
      </div>
      <details class="commandLog maintenanceTools">
        <summary>Εργαλεία συντήρησης</summary>
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
      </details>
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
        <span id="setupPasswordStatus" class="noteText">Το link ισχύει για 60 λεπτά και μπορεί να χρησιμοποιηθεί μία φορά.</span>
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
              <option value="pricing">pricing</option>
              <option value="tester">tester</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button id="inviteUserBtn" class="secondary">Αποστολή πρόσκλησης</button>
          <span id="inviteStatus" class="noteText"></span>
        </div>
        <div class="toolbar adminRoleBox">
          <label>Αλλαγή ρόλου <input id="roleUserIdentifierInput" type="text" placeholder="email ή #ID"></label>
          <label>Νέος ρόλος
            <select id="roleUpdateInput">
              <option value="user">user</option>
              <option value="pricing">pricing</option>
              <option value="tester">tester</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button id="updateUserRoleBtn" class="secondary">Αλλαγή ρόλου</button>
          <span id="roleUpdateStatus" class="noteText"></span>
        </div>
        <details class="adminSecretsBox" open>
          <summary>Secrets παραγωγής</summary>
          <div class="toolbar adminSecretsToolbar">
            <label>TEE username <input id="teeUsernameInput" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="Δεν εμφανίζεται η αποθηκευμένη τιμή"></label>
            <label>TEE password <input id="teePasswordInput" type="password" autocomplete="new-password" placeholder="Δεν εμφανίζεται η αποθηκευμένη τιμή"></label>
            <button id="saveTeeSecretsBtn" class="secondary">Αποθήκευση TEE</button>
            <span id="teeSecretsStatus" class="noteText">Φόρτωση κατάστασης...</span>
          </div>
        </details>
        <details class="adminUsersBox">
          <summary>Χρήστες</summary>
          <div class="tableWrap adminTableWrap adminUsersTableWrap">
            <table class="adminTable adminUsersTable">
              <thead>
                <tr>
                  <th>ID</th>
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
          <div><span id="adminDuplicateCandidateCount">0</span><small>πιθανά διπλότυπα</small></div>
          <div><span id="adminExpiredCount">0</span><small>ληγμένα</small></div>
          <div><span id="adminMissingDeadlineCount">0</span><small>χωρίς deadline</small></div>
          <div><span id="adminSourceErrorCount">0</span><small>source errors</small></div>
          <div><span id="adminReviewQueueCount">0</span><small>false-negative review</small></div>
          <div><span id="adminReviewHighCount">0</span><small>high priority</small></div>
        </div>
        <details class="adminReviewQueueBox" open>
          <summary>False negative review queue</summary>
          <div class="toolbar compact adminLazyToolbar">
            <button id="loadAdminReviewQueueBtn" class="secondary">Φόρτωση false-negative queue</button>
            <span id="adminReviewQueueStatus" class="noteText">Δεν έχει φορτωθεί η λίστα.</span>
          </div>
          <div class="tableWrap adminTableWrap adminLazyTableWrap">
            <table class="adminTable">
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Κατηγορία</th>
                  <th>Α/Α</th>
                  <th>Έργο</th>
                  <th>Γιατί θέλει έλεγχο</th>
                  <th>Ενέργεια</th>
                </tr>
              </thead>
              <tbody id="adminReviewRows"></tbody>
            </table>
          </div>
        </details>
        <details class="adminHiddenRowsBox">
          <summary>Κρυμμένα / audit rows</summary>
          <div class="toolbar compact adminLazyToolbar">
            <button id="loadAdminHiddenRowsBtn" class="secondary">Φόρτωση κρυμμένων έργων</button>
            <span id="adminHiddenRowsStatus" class="noteText">Δεν έχει φορτωθεί η λίστα.</span>
          </div>
          <div class="tableWrap adminTableWrap adminLazyTableWrap">
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
        </details>
      </div>
    </section>

    <section id="entalmata" class="view">
      <div class="searchBand">
        <div>
          <p class="eyebrow">Διαύγεια</p>
          <h3>Εντάλματα τελευταίων 15 ημερών</h3>
          <p class="mutedLine">Σαρώνει τους ρυθμισμένους φορείς Διαύγειας και κρατά αποφάσεις που περιέχουν τις λέξεις-κλειδιά ενδιαφέροντος.</p>
        </div>
        <div class="toolbar inlineToolbar">
          <button id="entalmataScanBtn">Νέα αναζήτηση ενταλμάτων</button>
          <button id="entalmataRefreshBtn" class="secondary">Ανανέωση λίστας</button>
        </div>
      </div>
      <div class="metrics">
        <div><span id="entalmataVisibleCount">0</span><small>εντάλματα 15ημέρου</small></div>
        <div><span id="entalmataArchivedCount">0</span><small>αρχειοθετημένα</small></div>
        <div><span id="entalmataOrgCount">0</span><small>φορείς</small></div>
        <div><span id="entalmataKeywordCount">0</span><small>λέξεις-κλειδιά</small></div>
      </div>
      <div id="entalmataRows" class="entalmataGrid"></div>
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
.textButton {
  min-height: auto;
  width: fit-content;
  padding: 0;
  background: transparent;
  color: var(--accent-dark);
  border: 0;
  font-weight: 800;
}
.textButton:hover {
  background: transparent;
  color: var(--accent);
}
.legalFooter {
  width: min(860px, 100%);
  display: grid;
  gap: 10px;
  margin: -44px auto 0;
  color: var(--muted);
}
.legalFooter details {
  border: 1px solid rgba(217, 221, 229, .85);
  border-radius: 10px;
  background: rgba(255,255,255,.78);
  padding: 12px 14px;
}
.legalFooter summary {
  cursor: pointer;
  color: var(--text);
  font-weight: 800;
}
.legalFooter p {
  margin-top: 8px;
  line-height: 1.55;
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
.view.active {
  display: block;
  max-width: 1720px;
  margin: 0 auto;
}
.searchBand {
  display: grid;
  grid-template-columns: minmax(360px, 1fr) minmax(440px, 620px);
  gap: 18px;
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
.interestProfileBox {
  margin-bottom: 14px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
.interestProfileBox summary {
  cursor: pointer;
  font-weight: 900;
  color: var(--text);
}
.interestProfileGrid {
  display: grid;
  grid-template-columns: minmax(220px, 1.15fr) minmax(220px, 1.15fr) minmax(180px, .85fr) minmax(180px, .85fr);
  gap: 12px;
  margin-top: 14px;
}
.interestProfileGrid textarea {
  resize: vertical;
  min-height: 76px;
}
.profileCategoryBox {
  margin: 12px 0 0;
  padding: 10px 0 0;
  border: 0;
  border-top: 1px solid var(--line);
}
.profileCategoryBox legend {
  padding: 0 6px 0 0;
  color: var(--text);
  font-weight: 900;
  font-size: 13px;
}
.profileCategoryOptions {
  display: grid;
  grid-template-columns: repeat(3, minmax(190px, 220px));
  justify-content: start;
  column-gap: 22px;
  row-gap: 4px;
  max-width: 760px;
}
.profileCategoryOption {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 6px;
  align-items: start;
  min-height: 20px;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
  font-size: 11.5px;
  font-weight: 700;
  line-height: 1.25;
}
.profileCategoryOption input {
  width: 12px;
  height: 12px;
  min-width: 0;
  min-height: 0;
  flex: 0 0 auto;
  margin: 1px 0 0;
  padding: 0;
  accent-color: #0f766e;
}
.profileCategoryOption span {
  overflow-wrap: normal;
  word-break: normal;
}
.profileCategoryOption:has(input:checked) {
  color: #0f766e;
}
.profileCategoryBox .noteText {
  display: block;
  margin-top: 8px;
  margin-bottom: 10px;
}
.profileCategoryBox + .toolbar.compact {
  margin-top: 8px;
}
.searchPanel {
  display: grid;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 14px;
}
.searchPanel h2 {
  font-size: 24px;
  margin: 0;
}
.deadlineWatch {
  display: grid;
  gap: 12px;
  margin-bottom: 14px;
}
.deadlineWatchHeader {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: end;
}
.deadlineWatchHeader h3 {
  margin: 0;
  font-size: 18px;
}
.deadlineBuckets {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.deadlineBucket {
  display: grid;
  gap: 8px;
  min-height: 116px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
.deadlineBucket strong {
  font-size: 24px;
  line-height: 1;
}
.deadlineBucket h4 {
  margin: 0;
  font-size: 13px;
}
.deadlineBucketList {
  display: grid;
  gap: 5px;
}
.deadlineBucketItem {
  display: block;
  min-height: 28px;
  padding: 5px 7px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  text-align: left;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.deadlineBucketItem:hover {
  border-color: #9fb6c9;
  background: #eef6f4;
}
.reverseSearchForm {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  gap: 10px;
  align-items: end;
}
.reverseSearchInputLabel input {
  width: 100%;
}
.reverseResults {
  display: grid;
  gap: 12px;
}
.reverseResultCard {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
.reverseResultHeader {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}
.reverseResultHeader h3 {
  margin: 0;
  font-size: 17px;
  line-height: 1.35;
}
.reverseMeta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  color: var(--muted);
  font-size: 13px;
}
.reverseMatchList {
  display: grid;
  gap: 8px;
}
.reverseMatch {
  display: grid;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #eef2f6;
}
.reverseMatch strong {
  color: var(--teal-dark);
  font-size: 13px;
}
.reverseMatch p {
  margin: 0;
  color: var(--muted);
  line-height: 1.45;
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
.adminLazyToolbar {
  margin-top: 10px;
}
.adminLazyTableWrap {
  max-height: 560px;
  overflow: auto;
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
.adminUsersTable {
  min-width: 760px;
}
.userIdBadge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef2f6;
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  font-weight: 850;
}
.adminUserEmail {
  display: inline-block;
  max-width: 100%;
  overflow-wrap: anywhere;
  font-weight: 800;
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
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 3px 7px;
  border-radius: 10px;
  background: var(--soft);
  color: var(--accent-dark);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.25;
  overflow-wrap: anywhere;
  white-space: normal;
}
.pillStack {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  align-items: flex-start;
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
.auditBox {
  border-color: #cbd5e1;
  background: #f8fafc;
}
.auditBox ul {
  display: grid;
  gap: 6px;
  margin: 8px 0 0;
  padding-left: 18px;
}
.auditBox li {
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
}
.auditBox strong {
  color: #0f172a;
}
.entalmataGrid {
  display: grid;
  gap: 12px;
}
.entalmaCard {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
.entalmaHeader {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}
.entalmaActions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.entalmaSubject {
  margin: 0;
  font-size: 16px;
  line-height: 1.35;
}
.entalmaMeta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px;
}
.entalmaMeta span {
  display: grid;
  gap: 2px;
  color: var(--text);
  font-weight: 700;
  overflow-wrap: anywhere;
}
.entalmaMeta small {
  color: var(--muted);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}
.entalmaKeywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
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
  .reverseSearchForm,
  .workspace {
    grid-template-columns: 1fr;
  }
  .interestProfileGrid {
    grid-template-columns: 1fr;
  }
  .profileCategoryOptions {
    grid-template-columns: 1fr;
    max-width: none;
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
  .legalFooter {
    margin-top: -28px;
  }
  .workspace {
    display: block;
  }
  .entalmaHeader,
  .entalmaMeta {
    grid-template-columns: 1fr;
    display: grid;
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
  .tenderTable thead,
  .adminTableWrap .adminTable thead {
    display: none;
  }
  .tenderTable,
  .tenderTable tbody,
  .tenderTable tr,
  .tenderTable td,
  .adminTableWrap .adminTable,
  .adminTableWrap .adminTable tbody,
  .adminTableWrap .adminTable tr,
  .adminTableWrap .adminTable td {
    display: block;
    width: 100%;
  }
  .tenderTable tr,
  .adminTableWrap .adminTable tr {
    margin-bottom: 12px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--panel);
    overflow: hidden;
  }
  .tenderTable td,
  .adminTableWrap .adminTable td {
    display: grid;
    grid-template-columns: minmax(146px, 38%) minmax(0, 1fr);
    gap: 12px;
    padding: 10px 12px;
    border-bottom: 1px solid #eef2f6;
    white-space: normal;
  }
  .tenderTable td::before,
  .adminTableWrap .adminTable td::before {
    content: attr(data-label);
    color: var(--muted);
    font-size: 11px;
    font-weight: 900;
    text-transform: uppercase;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .tenderTable td > *,
  .adminTableWrap .adminTable td > * {
    min-width: 0;
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
  adminSecrets: null,
  entalmata: null,
  reverseSearch: null,
  interestProfile: null,
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
    if (button.dataset.view === 'entalmata') {
      loadEntalmata().catch((error) => { $('statusText').textContent = String(error); });
    }
    if (button.dataset.view === 'workflow' && state.session && ['admin', 'pricing'].includes(state.session.role)) {
      loadPricingIngestStatus().catch((error) => { $('pricingIngestStatus').textContent = String(error); });
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
  await loadInterestProfile();
  await loadDashboard();
  await loadSourcePolling();
  if ($('entalmata').classList.contains('active')) {
    await loadEntalmata();
  }
  if ($('workflow').classList.contains('active') && state.session && ['admin', 'pricing'].includes(state.session.role)) {
    await loadPricingIngestStatus();
  }
  if ($('rules').classList.contains('active') && !state.evaluationConfig && $('ruleProfileSelect').value) {
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
  const sort = $('sortSelect').value || 'deadline_asc';
  const payload = await api(`/api/dashboard?scope=focus&sort=${sort}`);
  state.dashboard = payload;
  renderDashboard(payload);
}

async function loadInterestProfile() {
  const payload = await api('/api/user/interest-profile');
  state.interestProfile = payload;
  renderInterestProfile(payload);
}

function renderInterestProfile(payload) {
  const profile = (payload && payload.profile) || {};
  $('profileIncludeInput').value = (profile.include_keywords || []).join('\\n');
  $('profileExcludeInput').value = (profile.exclude_keywords || []).join('\\n');
  $('profileMinBudgetInput').value = profile.min_budget ?? '';
  $('profileMaxBudgetInput').value = profile.max_budget ?? '';
  renderProfileCategoryOptions(payload?.category_options || [], profile.category_ids || []);
  setInterestProfileStatus(Boolean(payload && payload.active), payload && payload.updated_at);
}

function renderProfileCategoryOptions(options, selectedIds) {
  const selected = new Set((selectedIds || []).map((value) => String(value)));
  const target = $('profileCategoryOptions');
  if (!options.length) {
    target.innerHTML = '<span class="noteText">Δεν υπάρχουν ακόμα διαθέσιμες κατηγορίες έργων.</span>';
    return;
  }
  target.innerHTML = options.map((option) => {
    const optionId = String(option.id || '');
    const checked = selected.has(optionId) ? ' checked' : '';
    return `
      <label class="profileCategoryOption">
        <input type="checkbox" data-profile-category-id="${escapeHtml(optionId)}"${checked}>
        <span>${escapeHtml(option.label || optionId)}</span>
      </label>
    `;
  }).join('');
}

function setInterestProfileStatus(active, updatedAt = '') {
  const suffix = updatedAt ? ` · ενημερώθηκε ${formatDateTime(updatedAt)}` : '';
  $('interestProfileStatus').textContent = active
    ? `Ενεργό προσωπικό φίλτρο${suffix}`
    : 'Χωρίς προσωπικούς περιορισμούς.';
}

function profileInputLines(id) {
  return String($(id).value || '')
    .split(/[,;\\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function profileBudgetInput(id) {
  const value = String($(id).value || '').trim();
  return value ? Number(value) : null;
}

function selectedProfileCategoryIds() {
  return Array.from(document.querySelectorAll('[data-profile-category-id]:checked'))
    .map((input) => input.dataset.profileCategoryId)
    .filter(Boolean);
}

async function saveInterestProfile() {
  $('interestProfileStatus').textContent = 'Αποθήκευση προφίλ...';
  const payload = await api('/api/user/interest-profile', {
    method: 'POST',
    body: JSON.stringify({
      profile: {
        include_keywords: profileInputLines('profileIncludeInput'),
        exclude_keywords: profileInputLines('profileExcludeInput'),
        category_ids: selectedProfileCategoryIds(),
        min_budget: profileBudgetInput('profileMinBudgetInput'),
        max_budget: profileBudgetInput('profileMaxBudgetInput'),
      },
    }),
  });
  state.interestProfile = payload;
  renderInterestProfile(payload);
  await loadDashboard();
}

async function loadSourcePolling() {
  const payload = await api('/api/source-polling');
  state.sourcePolling = payload;
  renderSourcePolling(payload);
}

async function loadEntalmata() {
  const payload = await api('/api/entalmata');
  state.entalmata = payload;
  renderEntalmata(payload);
}

async function runReverseSearch() {
  const query = $('reverseSearchInput').value.trim();
  $('reverseSearchStatus').textContent = query ? 'Αναζήτηση στα ενεργά έργα...' : 'Γράψε τουλάχιστον 2 χαρακτήρες.';
  const payload = await api('/api/reverse-search', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
  state.reverseSearch = payload;
  renderReverseSearch(payload);
}

async function runPricingActiveIngest() {
  const discoveryLimit = Math.max(1, Math.min(500, Number($('pricingDiscoveryLimit').value || 500)));
  const maxNewProjects = Math.max(1, Math.min(100, Number($('pricingMaxNewProjects').value || 15)));
  $('pricingIngestStatus').textContent = `Διαβάζουμε έως ${discoveryLimit} ενεργά έργα από ΕΣΗΔΗΣ και επεξεργαζόμαστε έως ${maxNewProjects} νέα/μη πλήρη...`;
  const initial = await api('/api/pricing/ingest-active', {
    method: 'POST',
    body: JSON.stringify({ discovery_limit: discoveryLimit, attachment_limit: 50, max_new_projects: maxNewProjects }),
  });
  if (!initial.job_id) {
    $('pricingIngestStatus').textContent = initial.error || 'Δεν ξεκίνησε η ενημέρωση pricing.';
    return;
  }
  const job = await pollJob(initial.job_id, 'Ενημέρωση βάσης αντίστροφης αναζήτησης');
  const result = job.result || {};
  const summary = result.summary || {};
  $('pricingIngestStatus').textContent = [
    `ΕΣΗΔΗΣ: ${summary.candidate_count || 0}`,
    `ελέγχθηκαν ${summary.inspected_count || 0}`,
    `νέα/μη πλήρη ${summary.attempted_new || 0}`,
    `ολοκληρωμένα ${summary.completed || 0}`,
    `ήδη πλήρη ${summary.skipped_existing || 0}`,
    `μερικά ${summary.partial || 0}`,
    `σφάλματα ${summary.failed || 0}`,
    `ζητούμενα υπόλοιπα ${summary.target_new_remaining || 0}`,
  ].join(' · ');
}

async function loadPricingIngestStatus() {
  try {
    const payload = await api('/api/pricing/ingest-status');
    renderPricingIngestStatus(payload);
  } catch (error) {
    $('pricingIngestStatus').textContent = 'Δεν μπόρεσε να φορτωθεί ο τελευταίος απολογισμός αντίστροφης ενημέρωσης.';
  }
}

function renderPricingIngestStatus(payload) {
  if (!payload || !payload.exists || !payload.run) {
    $('pricingIngestStatus').textContent = 'Δεν υπάρχει προηγούμενη ενημέρωση pricing στη βάση.';
    return;
  }
  const run = payload.run || {};
  const summary = payload.summary || {};
  const live = payload.live_counts || {};
  const parts = [
    `τελευταίο run ${run.status || 'UNKNOWN'}`,
    run.started_at ? `έναρξη ${run.started_at}` : '',
  ];
  if (run.finished_at) parts.push(`λήξη ${run.finished_at}`);
  if (summary.candidate_count !== undefined) parts.push(`ΕΣΗΔΗΣ ${summary.candidate_count || 0}`);
  if (summary.inspected_count !== undefined) parts.push(`ελέγχθηκαν ${summary.inspected_count || 0}`);
  if (summary.attempted_new !== undefined) parts.push(`νέα/μη πλήρη ${summary.attempted_new || 0}`);
  if (summary.completed !== undefined) parts.push(`ολοκληρωμένα ${summary.completed || 0}`);
  if (summary.failed !== undefined) parts.push(`σφάλματα ${summary.failed || 0}`);
  if (run.status === 'RUNNING') {
    parts.push(`τρέχοντα projects ${live.projects || 0}`);
    parts.push(`documents ${live.documents || 0}`);
    parts.push(`text ${live.text_docs || 0}`);
    parts.push(`merged rows ${live.merged_rows || 0}`);
  }
  $('pricingIngestStatus').textContent = parts.filter(Boolean).join(' · ');
}

function renderReverseSearch(payload) {
  const summary = payload.summary || {};
  $('reverseMatchCount').textContent = summary.matches || 0;
  $('reverseSearchedCount').textContent = summary.active_rows_searched || 0;
  $('reverseSearchStatus').textContent = payload.query
    ? `${summary.matches || 0} έργα βρέθηκαν για “${payload.query}”.`
    : (payload.empty_message || 'Γράψε έναν όρο για να ξεκινήσεις.');
  const container = $('reverseSearchResults');
  container.innerHTML = '';
  const results = payload.results || [];
  if (!results.length) {
    container.innerHTML = `<div class="emptyState">${escapeHtml(payload.empty_message || 'Δεν υπάρχουν αποτελέσματα.')}</div>`;
    return;
  }
  for (const item of results) {
    const card = document.createElement('article');
    card.className = 'reverseResultCard';
    const matches = (item.matches || []).map((match) => `
      <div class="reverseMatch">
        <strong>${escapeHtml(match.label || match.kind || 'match')}</strong>
        <p>${escapeHtml(match.snippet || '')}</p>
      </div>
    `).join('');
    card.innerHTML = `
      <div class="reverseResultHeader">
        <div>
          <p class="eyebrow">${escapeHtml(item.source_label || '')} ${escapeHtml(item.display_id || '')}</p>
          <h3>${escapeHtml(item.title || '')}</h3>
        </div>
        ${item.official_url ? `<a class="button tinyButton secondary" href="${escapeHtml(item.official_url)}" target="_blank" rel="noreferrer">Open</a>` : ''}
      </div>
      <div class="reverseMeta">
        <span>${escapeHtml(item.authority_name || '')}</span>
        <span>${escapeHtml(item.budget_display || '')}</span>
        <span>${escapeHtml(item.deadline_display || '')}</span>
      </div>
      <div class="reverseMatchList">${matches}</div>
    `;
    container.appendChild(card);
  }
}

function renderEntalmata(payload) {
  const summary = payload.summary || {};
  $('entalmataVisibleCount').textContent = summary.visible || 0;
  $('entalmataArchivedCount').textContent = summary.archived || 0;
  $('entalmataOrgCount').textContent = summary.configured_organizations || 0;
  $('entalmataKeywordCount').textContent = summary.keywords || 0;
  const container = $('entalmataRows');
  container.innerHTML = '';
  const records = payload.records || [];
  if (!records.length) {
    container.innerHTML = '<div class="emptyState">Δεν υπάρχουν ακόμα εντάλματα στο τελευταίο 15ήμερο. Πάτα νέα αναζήτηση για σάρωση Διαύγειας.</div>';
    return;
  }
  for (const item of records) {
    const card = document.createElement('article');
    card.className = 'entalmaCard';
    const keywords = (item.matched_keywords || [])
      .map((keyword) => `<span class="pill">${escapeHtml(keyword)}</span>`)
      .join('');
    const localPdfUrl = item.local_path || item.archive_path ? `/api/entalmata-file?ada=${encodeURIComponent(item.ada || '')}` : '';
    card.innerHTML = `
      <div class="entalmaHeader">
        <div>
          <p class="eyebrow">ΑΔΑ ${escapeHtml(item.ada || '')}</p>
          <h3 class="entalmaSubject">${escapeHtml(item.subject || '')}</h3>
        </div>
        <div class="entalmaActions">
          ${localPdfUrl ? `<a class="button tinyButton" href="${escapeHtml(localPdfUrl)}" target="_blank" rel="noreferrer">PDF</a>` : ''}
          ${item.document_url ? `<a class="button tinyButton secondary" href="${escapeHtml(item.document_url)}" target="_blank" rel="noreferrer">Διαύγεια</a>` : ''}
        </div>
      </div>
      <div class="entalmaMeta">
        <span><small>Φορέας</small>${escapeHtml(item.org_name || item.org_id || '')}</span>
        ${item.project_title ? `<span><small>Τίτλος έργου</small>${escapeHtml(item.project_title)}</span>` : ''}
        <span><small>Ημερομηνία</small>${escapeHtml(item.issue_date || '')}</span>
        <span><small>Πρωτόκολλο</small>${escapeHtml(item.protocol_number || '')}</span>
      </div>
      <div class="entalmaKeywords">${keywords || '<span class="pill">χωρίς keyword</span>'}</div>
      ${item.text_sample ? `<p class="noteText">${escapeHtml(item.text_sample)}</p>` : ''}
    `;
    container.appendChild(card);
  }
}

async function refreshRuntimeViews() {
  await loadDashboard();
  await loadSourcePolling();
  if ($('entalmata').classList.contains('active')) {
    await loadEntalmata();
  }
  if (!$('adminContent').hidden) {
    await loadAdminAudit();
  }
  if ($('workflow').classList.contains('active') && state.session && ['admin', 'pricing'].includes(state.session.role)) {
    await loadPricingIngestStatus();
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

async function requestPasswordReset() {
  const email = $('loginEmailInput').value.trim();
  if (!email) {
    $('loginStatus').textContent = 'Γράψε πρώτα το email σου.';
    return;
  }
  $('loginStatus').textContent = 'Στέλνω link επαναφοράς...';
  try {
    await adminApi('/api/auth/request-password-reset', { method: 'POST', body: JSON.stringify({ email }) });
    $('loginStatus').textContent = 'Αν το email είναι καταχωρημένο, στάλθηκε link ορισμού νέου password.';
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

async function updateUserRole() {
  const identifier = $('roleUserIdentifierInput').value;
  const role = $('roleUpdateInput').value;
  $('roleUpdateStatus').textContent = 'Αλλάζω ρόλο...';
  try {
    await adminApi('/api/admin/update-user-role', { method: 'POST', body: JSON.stringify({ identifier, role }) });
    $('roleUserIdentifierInput').value = '';
    $('roleUpdateStatus').textContent = 'Ο ρόλος ενημερώθηκε.';
    await loadAdminUsers();
  } catch (error) {
    $('roleUpdateStatus').textContent = String(error.message || error);
  }
}

async function loadAdminUsers() {
  const payload = await adminApi('/api/admin/users');
  const tbody = $('adminUsersRows');
  tbody.innerHTML = '';
  const users = payload.users || [];
  if (!users.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="emptyState">Δεν υπάρχουν χρήστες.</td></tr>';
    return;
  }
  for (const user of users) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td data-label="ID"><span class="userIdBadge">#${escapeHtml(user.id || '')}</span></td>
      <td data-label="Email"><span class="adminUserEmail">${escapeHtml(user.email || '')}</span></td>
      <td data-label="Ρόλος"><span class="statusChip unchanged">${escapeHtml(user.role || '')}</span></td>
      <td data-label="Password">${user.password_set ? 'Ορισμένο' : 'Σε πρόσκληση'}</td>
      <td data-label="Τελευταία σύνδεση">${escapeHtml(user.last_login_at || '')}</td>
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

async function loadAdminAudit(include = 'summary') {
  if (!state.session || state.session.role !== 'admin') {
    $('adminContent').hidden = true;
    $('adminLockedBox').hidden = false;
    return;
  }
  try {
    const payload = await adminApi(`/api/admin/audit?include=${encodeURIComponent(include)}`);
    state.adminAudit = { ...(state.adminAudit || {}), ...payload };
    $('adminLockedBox').hidden = true;
    $('adminContent').hidden = false;
    renderAdminAudit(state.adminAudit, include);
    if (include === 'summary') {
      await loadAdminSecrets();
      await loadAdminUsers();
    }
  } catch (error) {
    $('adminContent').hidden = true;
    $('adminLockedBox').hidden = false;
  }
}

async function loadAdminSecrets() {
  const payload = await adminApi('/api/admin/secrets');
  state.adminSecrets = payload;
  renderAdminSecrets(payload);
}

function renderAdminSecrets(payload) {
  const keys = payload.keys || {};
  const username = keys.TEE_USERNAME?.configured ? 'TEE_USERNAME αποθηκευμένο' : 'TEE_USERNAME λείπει';
  const password = keys.TEE_PASSWORD?.configured ? 'TEE_PASSWORD αποθηκευμένο' : 'TEE_PASSWORD λείπει';
  $('teeSecretsStatus').textContent = `${username} · ${password}`;
}

async function saveTeeSecrets() {
  const username = $('teeUsernameInput').value;
  const password = $('teePasswordInput').value;
  const payload = {};
  if (username) payload.TEE_USERNAME = username;
  if (password) payload.TEE_PASSWORD = password;
  if (!Object.keys(payload).length) {
    $('teeSecretsStatus').textContent = 'Συμπλήρωσε username ή password για αποθήκευση.';
    return;
  }
  $('teeSecretsStatus').textContent = 'Αποθήκευση στο .env.local...';
  const result = await adminApi('/api/admin/secrets', { method: 'POST', body: JSON.stringify(payload) });
  $('teeUsernameInput').value = '';
  $('teePasswordInput').value = '';
  renderAdminSecrets(result);
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
  $('pricingNavBtn').hidden = !session || !['admin', 'pricing'].includes(session.role);
  if (isLoggedIn && session.role !== 'admin' && $('adminPanel').classList.contains('active')) {
    document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
    document.querySelector('[data-view="overview"]').classList.add('active');
    $('overview').classList.add('active');
  }
  if (isLoggedIn && !['admin', 'pricing'].includes(session.role) && $('workflow').classList.contains('active')) {
    document.querySelectorAll('.nav, .view').forEach((el) => el.classList.remove('active'));
    document.querySelector('[data-view="overview"]').classList.add('active');
    $('overview').classList.add('active');
  }
}

function renderAdminAudit(payload, include = 'summary') {
  const summary = payload.summary || {};
  $('adminHiddenCount').textContent = summary.hidden_total || 0;
  $('adminAiHiddenCount').textContent = summary.ai_hidden || 0;
  $('adminDismissedCount').textContent = summary.dismissed || 0;
  $('adminDuplicateCount').textContent = summary.duplicates || 0;
  $('adminDuplicateCandidateCount').textContent = summary.duplicate_candidates || 0;
  $('adminExpiredCount').textContent = summary.expired || 0;
  $('adminMissingDeadlineCount').textContent = summary.missing_deadline || 0;
  $('adminSourceErrorCount').textContent = summary.source_errors || 0;
  $('adminReviewQueueCount').textContent = summary.review_queue_total || 0;
  $('adminReviewHighCount').textContent = summary.review_queue_high || 0;
  if (include === 'summary') {
    renderAdminReviewQueue(null);
    renderAdminHiddenRows(null);
    $('adminReviewQueueStatus').textContent = `${summary.review_queue_total || 0} rows διαθέσιμα. Πάτα φόρτωση όταν τα χρειάζεσαι.`;
    $('adminHiddenRowsStatus').textContent = `${summary.hidden_total || 0} rows διαθέσιμα. Πάτα φόρτωση όταν τα χρειάζεσαι.`;
    return;
  }
  if (include === 'review' || include === 'all') {
    renderAdminReviewQueue(payload.review_queue || []);
    $('adminReviewQueueStatus').textContent = `${(payload.review_queue || []).length} rows φορτώθηκαν.`;
  }
  if (include === 'hidden' || include === 'all') {
    renderAdminHiddenRows(payload.hidden_rows || []);
    $('adminHiddenRowsStatus').textContent = `${(payload.hidden_rows || []).length} rows φορτώθηκαν.`;
  }
}

function renderAdminHiddenRows(rows) {
  const tbody = $('adminHiddenRows');
  tbody.innerHTML = '';
  if (rows === null) {
    tbody.innerHTML = '<tr><td colspan="6" class="emptyState">Η λίστα δεν φορτώνεται αυτόματα για να μένει γρήγορο το admin panel.</td></tr>';
    return;
  }
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
    const titlePills = [
      row.ai_decision ? escapeHtml(row.ai_decision) : '',
      row.ai_confidence_band?.label ? escapeHtml(row.ai_confidence_band.label) : '',
      row.profile_fit?.label ? escapeHtml(row.profile_fit.label) : '',
      row.audit_match ? `match ${escapeHtml(row.audit_match.eshidis_id || '')} · ${escapeHtml(row.audit_match.score || '')}` : '',
      row.feedback_action ? `feedback ${escapeHtml(row.feedback_action)}` : '',
    ].filter(Boolean).map((label) => `<span class="pill">${label}</span>`).join('');
    tr.innerHTML = `
      <td data-label="Κατηγορία"><span class="statusChip ${adminCategoryClass(row.category)}">${escapeHtml(adminCategoryLabel(row.category))}</span></td>
      <td data-label="Α/Α"><strong>${escapeHtml(row.display_id || '')}</strong><br><span class="noteText">${escapeHtml(row.source_label || '')}</span>${row.audit_at ? `<br><span class="noteText">${escapeHtml(formatDateTime(row.audit_at))}</span>` : ''}</td>
      <td data-label="Έργο" class="tenderTitle">${escapeHtml(row.title || '')}${titlePills ? `<span class="pillStack">${titlePills}</span>` : ''}</td>
      <td data-label="Φορέας" class="authorityCell">${escapeHtml(row.authority_name || '')}</td>
      <td data-label="Αιτιολογία">${escapeHtml(row.reason || '')}${row.ai_confidence_band?.reason ? `<br><span class="noteText">${escapeHtml(row.ai_confidence_band.reason)}</span>` : ''}${row.ai_confidence ? `<br><span class="noteText">confidence ${escapeHtml(row.ai_confidence)}</span>` : ''}</td>
      <td data-label="Ενέργεια"><div class="actionStack">${sourceLink}${restoreButton}</div></td>
    `;
    tbody.appendChild(tr);
  }
  document.querySelectorAll('#adminHiddenRows .restoreHiddenRow').forEach((button) => {
    button.addEventListener('click', () => restoreHiddenRow(button.dataset.key, 'hidden'));
  });
}

function renderAdminReviewQueue(rows) {
  const tbody = $('adminReviewRows');
  tbody.innerHTML = '';
  if (rows === null) {
    tbody.innerHTML = '<tr><td colspan="6" class="emptyState">Η λίστα δεν φορτώνεται αυτόματα. Πάτα φόρτωση για έλεγχο false negatives.</td></tr>';
    return;
  }
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="emptyState">Δεν υπάρχουν rows για false-negative review.</td></tr>';
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
    const feedbackLabel = row.feedback_action
      ? `<span class="noteText">feedback ${escapeHtml(row.feedback_action)}</span>`
      : '';
    tr.innerHTML = `
      <td data-label="Priority"><span class="statusChip ${reviewPriorityClass(row.review_priority)}">${escapeHtml(row.review_priority || '')}</span></td>
      <td data-label="Κατηγορία"><span class="statusChip ${adminCategoryClass(row.category)}">${escapeHtml(adminCategoryLabel(row.category))}</span></td>
      <td data-label="Α/Α"><strong>${escapeHtml(row.display_id || '')}</strong><br><span class="noteText">${escapeHtml(row.source_label || '')}</span>${row.audit_at ? `<br><span class="noteText">${escapeHtml(formatDateTime(row.audit_at))}</span>` : ''}</td>
      <td data-label="Έργο" class="tenderTitle">${escapeHtml(row.title || '')}</td>
      <td data-label="Γιατί θέλει έλεγχο">${escapeHtml(row.review_reason || '')}<br><span class="noteText">${escapeHtml(row.reason || '')}</span>${row.ai_confidence_band?.label ? `<br><span class="noteText">${escapeHtml(row.ai_confidence_band.label)} · ${escapeHtml(row.ai_confidence_band.reason || '')}</span>` : ''}${row.ai_confidence ? `<br><span class="noteText">confidence ${escapeHtml(row.ai_confidence)}</span>` : ''}</td>
      <td data-label="Ενέργεια"><div class="actionStack">
        ${sourceLink}
        <button class="tinyButton confirmDropReview" data-key="${escapeHtml(row.row_key)}">Σωστά κόπηκε</button>
        <button class="tinyButton keepReviewRow" data-key="${escapeHtml(row.row_key)}">Λάθος, κράτα τέτοια</button>
        ${restoreButton}
        ${feedbackLabel}
      </div></td>
    `;
    tbody.appendChild(tr);
  }
  document.querySelectorAll('.confirmDropReview').forEach((button) => {
    button.addEventListener('click', () => adminReviewFeedback(button.dataset.key, 'CONFIRM_DROP'));
  });
  document.querySelectorAll('.keepReviewRow').forEach((button) => {
    button.addEventListener('click', () => adminReviewFeedback(button.dataset.key, 'FORCE_KEEP'));
  });
  document.querySelectorAll('#adminReviewRows .restoreHiddenRow').forEach((button) => {
    button.addEventListener('click', () => restoreHiddenRow(button.dataset.key, 'review'));
  });
}

function reviewPriorityClass(priority) {
  if (priority === 'HIGH') return 'error';
  if (priority === 'MEDIUM') return 'changed';
  if (priority === 'LOW') return 'waiting';
  return 'waiting';
}

function adminCategoryLabel(category) {
  return {
    AI_HIDDEN: 'AI',
    AI_DROP_ADMIN: 'Διοικητικό',
    AI_DROP_SUPPLY_SERVICE: 'Προμήθεια/υπηρεσία',
    AI_DROP_NOT_PUBLIC_WORKS: 'Όχι δημόσιο έργο',
    AI_EARLY_SIGNAL: 'Πρώιμο σήμα',
    DISMISSED: 'Δεν με ενδιαφέρει',
    DUPLICATE: 'Διπλότυπο',
    DUPLICATE_CANDIDATE: 'Πιθανό διπλότυπο',
    EXPIRED: 'Ληγμένο',
    NO_DEADLINE_EVIDENCE: 'Χωρίς deadline',
    OUT_OF_SCOPE_SUPPLY_SERVICE: 'Προμήθεια/υπηρεσία',
  }[category] || category || 'Άγνωστο';
}

function adminCategoryClass(category) {
  if (category === 'AI_HIDDEN') return 'waiting';
  if (category === 'AI_DROP_ADMIN') return 'waiting';
  if (category === 'AI_DROP_SUPPLY_SERVICE') return 'waiting';
  if (category === 'AI_DROP_NOT_PUBLIC_WORKS') return 'waiting';
  if (category === 'AI_EARLY_SIGNAL') return 'waiting';
  if (category === 'DISMISSED') return 'error';
  if (category === 'DUPLICATE') return 'unchanged';
  if (category === 'DUPLICATE_CANDIDATE') return 'unchanged';
  if (category === 'EXPIRED') return 'changed';
  if (category === 'NO_DEADLINE_EVIDENCE') return 'waiting';
  if (category === 'OUT_OF_SCOPE_SUPPLY_SERVICE') return 'waiting';
  return 'waiting';
}

async function restoreHiddenRow(rowKey, include = 'summary') {
  if (!rowKey) return;
  const reason = window.prompt('Γιατί επαναφέρεις αυτό το έργο; Αυτό θα χρησιμοποιηθεί ως feedback για τους επόμενους κανόνες.', '');
  if (reason === null) return;
  await adminApi('/api/admin/restore', { method: 'POST', body: JSON.stringify({ row_key: rowKey, reason }) });
  await refreshRuntimeViews();
  await loadAdminAudit(include);
}

async function adminReviewFeedback(rowKey, action) {
  if (!rowKey) return;
  let reason = '';
  if (action === 'FORCE_KEEP') {
    const answer = window.prompt('Γιατί πρέπει να κρατάμε τέτοια έργα;', '');
    if (answer === null) return;
    reason = answer;
  }
  await adminApi('/api/admin/review-feedback', { method: 'POST', body: JSON.stringify({ row_key: rowKey, action, reason }) });
  await refreshRuntimeViews();
  await loadAdminAudit('review');
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
    ['Health warnings', summary.health_warning_total || 0],
    ['Disable candidates', summary.disable_candidate_total || 0],
    ['Templates', summary.requires_identifier_total || 0],
    ['Never checked', summary.never_checked_total || 0],
  ].map(([label, value]) => `<span class="sourceAuditMetric">${escapeHtml(label)} ${escapeHtml(value)}</span>`).join('');
  const tbody = $('sourceAuditRows');
  tbody.innerHTML = '';
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="emptyState">Δεν έχει τρέξει ακόμα source polling σε αυτό το runtime.</td></tr>';
    return;
  }
  for (const source of rows) {
    const statusClass = sourceStatusClass(source.last_status, source.last_error);
    const health = source.health || {};
    const healthClass = sourceHealthClass(health.status);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <span class="sourceAuditSource">${escapeHtml(source.name || source.source_id)}</span>
        <span class="sourceAuditUrl">${escapeHtml(source.source_id || '')}${source.source_url ? ` · ${escapeHtml(source.source_url)}` : ''}</span>
      </td>
      <td>${escapeHtml(source.family_or_adapter || '')}</td>
      <td><span class="statusChip ${statusClass}">${escapeHtml(source.last_status || 'UNKNOWN')}</span></td>
      <td>
        <span class="statusChip ${healthClass}">${escapeHtml(health.label || health.status || 'Άγνωστο')}</span>
        <br><span class="noteText">${escapeHtml(health.recent_failures || 0)}/${escapeHtml(health.recent_checks || 0)} failures · streak ${escapeHtml(health.consecutive_failures || 0)}</span>
        ${health.last_success_at ? `<br><span class="noteText">last ok ${escapeHtml(formatDateTime(health.last_success_at))}</span>` : ''}
        ${health.recommendation ? `<br><span class="noteText">${escapeHtml(health.recommendation)}</span>` : ''}
      </td>
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

function sourceHealthClass(status) {
  if (status === 'DISABLE_CANDIDATE') return 'error';
  if (status === 'DEGRADED') return 'changed';
  if (status === 'WATCH') return 'waiting';
  if (status === 'HEALTHY') return 'unchanged';
  return 'waiting';
}

function formatDateTime(value) {
  if (!value) return '';
  return String(value).replace('T', ' ').replace('+00:00', ' UTC');
}

function pillStack(labels) {
  const pills = (labels || [])
    .filter((label) => label !== null && label !== undefined && String(label).trim())
    .map((label) => `<span class="pill">${escapeHtml(label)}</span>`)
    .join('');
  return pills ? `<span class="pillStack">${pills}</span>` : '';
}

function renderDashboard(payload) {
  $('visibleTenderCount').textContent = payload.summary.visible || 0;
  $('focusTenderCount').textContent = payload.summary.focus_matches || 0;
  const municipalityText = (payload.profile.municipalities || []).join(', ');
  const userProfileActive = Boolean(payload.profile.user_interest_active);
  $('scopeText').textContent = userProfileActive
    ? `Προεπιλογή τοπικού ενδιαφέροντος: ${municipalityText}. Εφαρμόζεται και το προσωπικό προφίλ σου.`
    : `Προεπιλογή τοπικού ενδιαφέροντος: ${municipalityText}`;
  setInterestProfileStatus(userProfileActive, payload.profile.user_interest_updated_at || '');
  renderDiscoverySafety(payload.discovery_run);
  renderDeadlineWatch(payload.tenders || []);
  const rows = $('tenderRows');
  rows.innerHTML = '';
  if (!payload.tenders.length) {
    rows.innerHTML = '<tr><td colspan="7" class="emptyState">Δεν υπάρχουν ακόμα έργα για την τοπική περιοχή ενδιαφέροντος. Δοκίμασε νέα αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ.</td></tr>';
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
    const titlePills = pillStack([
      tender.interest_reason || '',
      tender.official_status_label || '',
      (tender.linked_eshidis_ids || []).length ? `ΕΣΗΔΗΣ ${(tender.linked_eshidis_ids || []).join(', ')}` : '',
      tender.category_audit?.primary?.label || '',
      tender.profile_fit?.label || '',
      tender.ai_confidence_band?.label || tender.ai_triage?.decision || '',
    ]);
    const zipUrl = `/api/document-zip?identifier=${encodeURIComponent(fetchIdentifier)}`;
    const tr = document.createElement('tr');
    tr.dataset.key = rowKey;
    if (state.selected === rowKey) tr.classList.add('selectedRow');
    tr.innerHTML = `
      <td data-label="Α/Α"><strong>${escapeHtml(tender.display_id || tender.eshidis_id || '')}</strong></td>
      <td data-label="Πηγή">${escapeHtml(tender.source_label || '')}</td>
      <td data-label="Έργο" class="tenderTitle">${escapeHtml(tender.title || '')}${titlePills}</td>
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

function renderDeadlineWatch(tenders) {
  const buckets = deadlineWatchBuckets(tenders || []);
  const totalActionRows = buckets.reduce((sum, bucket) => sum + bucket.rows.length, 0);
  $('deadlineWatchSummary').textContent = `${totalActionRows} ενδείξεις από ${tenders.length || 0} ενεργά έργα`;
  $('deadlineWatchBuckets').innerHTML = buckets.map((bucket) => `
    <article class="deadlineBucket">
      <div>
        <strong>${escapeHtml(bucket.rows.length)}</strong>
        <h4>${escapeHtml(bucket.label)}</h4>
      </div>
      <div class="deadlineBucketList">
        ${bucket.rows.slice(0, 3).map((row) => deadlineBucketItem(row)).join('') || '<span class="noteText">Καμία άμεση ενέργεια</span>'}
      </div>
    </article>
  `).join('');
  document.querySelectorAll('.deadlineBucketItem').forEach((button) => {
    button.addEventListener('click', () => selectTender(button.dataset.key, false));
  });
}

function deadlineWatchBuckets(tenders) {
  const rows = [...(tenders || [])];
  return [
    { id: 'tomorrow', label: 'Λήγουν αύριο', rows: rows.filter((row) => daysUntilDeadline(row) === 1) },
    { id: 'threeDays', label: 'Λήγουν σε 3 ημέρες', rows: rows.filter((row) => inDeadlineWindow(row, 0, 3)) },
    { id: 'sevenDays', label: 'Λήγουν σε 7 ημέρες', rows: rows.filter((row) => inDeadlineWindow(row, 0, 7)) },
    { id: 'missingEmail', label: 'Χωρίς email', rows: rows.filter((row) => operationStatus(row, 'Email') !== 'sent') },
    { id: 'missingDocs', label: 'Χωρίς έγγραφα', rows: rows.filter((row) => operationStatus(row, 'Έγγραφα') === 'pending') },
    { id: 'missingEshidis', label: 'Χωρίς ΕΣΗΔΗΣ', rows: rows.filter((row) => !row.eshidis_id && !(row.linked_eshidis_ids || []).length) },
  ].map((bucket) => ({ ...bucket, rows: bucket.rows.sort(deadlineWatchSort) }));
}

function deadlineBucketItem(row) {
  const rowKey = row.row_key || row.eshidis_id || row.display_id || '';
  const title = row.title || row.display_id || rowKey;
  const meta = [row.deadline_display || '', row.source_label || ''].filter(Boolean).join(' · ');
  return `<button class="deadlineBucketItem" data-key="${escapeHtml(rowKey)}">${escapeHtml(title)}${meta ? `<br><span class="noteText">${escapeHtml(meta)}</span>` : ''}</button>`;
}

function operationStatus(row, label) {
  const item = (row.project_operations || []).find((operation) => operation.label === label);
  return item ? item.status : '';
}

function inDeadlineWindow(row, minDays, maxDays) {
  const days = daysUntilDeadline(row);
  return days !== null && days >= minDays && days <= maxDays;
}

function daysUntilDeadline(row) {
  const sortKey = String(row.deadline_sort || '').trim();
  const match = sortKey.match(/^(\\d{4})-(\\d{2})-(\\d{2})/);
  if (!match) return null;
  const deadline = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const today = new Date();
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.floor((deadline - todayStart) / 86400000);
}

function deadlineWatchSort(left, right) {
  return String(left.deadline_sort || '9999').localeCompare(String(right.deadline_sort || '9999'))
    || String(left.display_id || '').localeCompare(String(right.display_id || ''));
}

function renderDiscoverySafety(run) {
  if (!run) {
    $('discoverySafetyText').textContent = 'Δεν υπάρχει ακόμη ιστορικό τελευταίας αναζήτησης.';
    return;
  }
  const depth = run.depth || {};
  const watermark = run.watermark || {};
  const status = run.success
    ? 'τελευταία αναζήτηση ολοκληρώθηκε'
    : (run.source_success ? 'τελευταία αναζήτηση με ατελές ιστορικό' : 'τελευταία αναζήτηση με μερική αποτυχία πηγής');
  const mode = run.mode === 'backfill' ? 'με έλεγχο backfill' : 'γρήγορη';
  const complete = watermark.complete ? 'καλύφθηκε το αποθηκευμένο ιστορικό' : 'ίσως χρειάζεται βαθύτερος έλεγχος';
  $('discoverySafetyText').textContent = `${status} · ${mode} · ΕΣΗΔΗΣ ${depth.eshidis_limit || '-'} · ΚΗΜΔΗΣ ${depth.kimdis_pages_per_family || '-'} σελίδες · ${complete}`;
}

function resetPreview() {
  $('previewTitle').textContent = 'Διάλεξε έργο';
  $('officialLink').removeAttribute('href');
  $('previewBody').innerHTML = '<p class="mutedLine">Εδώ θα εμφανιστούν η διακήρυξη, η τεχνική περιγραφή και ο προϋπολογισμός όταν υπάρχουν κατεβασμένα ή γνωστά συνημμένα.</p>';
}

function renderTenderExplanation(tender) {
  const reasons = tender.why_visible || [];
  const sources = tender.project_sources || [];
  const operations = tender.project_operations || [];
  const timeline = tender.project_timeline || [];
  const identity = tender.project_identity || {};
  const sourceMerge = tender.source_merge || {};
  const profileFit = tender.profile_fit || null;
  const confidenceBand = tender.ai_confidence_band || null;
  const categoryAudit = tender.category_audit || {};
  if (!reasons.length && !sources.length && !operations.length && !timeline.length && !identity.canonical_label && !sourceMerge.label && !profileFit && !confidenceBand && !(categoryAudit.labels || []).length) return '';
  const identityItems = [
    identity.canonical_label ? `<li><strong>Κύρια ταυτότητα</strong>: ${escapeHtml(identity.canonical_label)}</li>` : '',
    identity.primary_source ? `<li><strong>Κύρια πηγή</strong>: ${escapeHtml(identity.primary_source)}</li>` : '',
    sourceMerge.label ? `<li><strong>Dedup</strong>: ${escapeHtml(sourceMerge.label)}${sourceMerge.reason ? ` · ${escapeHtml(sourceMerge.reason)}` : ''}</li>` : '',
  ].filter(Boolean).join('');
  const profileItems = [
    profileFit ? `<li><strong>Προφίλ</strong>: ${escapeHtml(profileFit.label || '')}${profileFit.reason ? ` · ${escapeHtml(profileFit.reason)}` : ''}</li>` : '',
    confidenceBand ? `<li><strong>AI band</strong>: ${escapeHtml(confidenceBand.label || '')}${confidenceBand.reason ? ` · ${escapeHtml(confidenceBand.reason)}` : ''}</li>` : '',
  ].filter(Boolean).join('');
  const categoryItems = (categoryAudit.labels || []).map((item) => {
    const evidence = (item.evidence || []).map((ev) => `${ev.kind || 'σήμα'}: ${ev.text || ''}`).join(' · ');
    const polarity = item.polarity === 'negative' ? 'αρνητικό' : 'θετικό';
    return `<li><strong>${escapeHtml(item.label || '')}</strong> · ${polarity} · confidence ${escapeHtml(item.confidence ?? '')}${evidence ? `<br><span class="noteText">${escapeHtml(evidence)}</span>` : ''}</li>`;
  }).join('');
  const reasonItems = reasons.map((item) => `
    <li><strong>${escapeHtml(item.label || '')}</strong>${item.label ? ': ' : ''}${escapeHtml(item.text || '')}</li>
  `).join('');
  const sourceItems = sources.map((item) => `
    <li><strong>${escapeHtml(item.label || '')}</strong>${item.identifier ? ` ${escapeHtml(item.identifier)}` : ''}${item.primary === 'true' ? ' · primary' : ''}${item.role ? ` · ${escapeHtml(item.role)}` : ''}${item.status ? ` · ${escapeHtml(item.status)}` : ''}${item.merge_level ? ` · ${escapeHtml(item.merge_level)}` : ''}${item.url ? ` · <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Open</a>` : ''}</li>
  `).join('');
  const operationItems = operations.map((item) => `
    <li><strong>${escapeHtml(item.label || '')}</strong>${item.status ? ` · ${escapeHtml(item.status)}` : ''}: ${escapeHtml(item.text || '')}</li>
  `).join('');
  const timelineItems = timeline.map((item) => `
    <li><strong>${escapeHtml(item.label || '')}</strong>${item.label ? ': ' : ''}${escapeHtml(item.text || '')}${item.at ? ` · ${escapeHtml(formatDateTime(item.at))}` : ''}</li>
  `).join('');
  return `
    <section class="docItem auditBox">
      <h4>Γιατί εμφανίζεται</h4>
      ${identityItems ? `<h4>Ταυτότητα έργου</h4><ul>${identityItems}</ul>` : ''}
      ${profileItems ? `<ul>${profileItems}</ul>` : ''}
      ${categoryItems ? `<h4>Κατηγοριοποίηση</h4><p class="noteText">${escapeHtml(categoryAudit.summary || '')}</p><ul>${categoryItems}</ul>` : ''}
      ${reasonItems ? `<ul>${reasonItems}</ul>` : ''}
      ${sourceItems ? `<h4>Πηγές</h4><ul>${sourceItems}</ul>` : ''}
      ${operationItems ? `<h4>Κατάσταση</h4><ul>${operationItems}</ul>` : ''}
      ${timelineItems ? `<h4>Timeline</h4><ul>${timelineItems}</ul>` : ''}
    </section>
  `;
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
    await renderAuthorityPreview(tender.row_key || eshidisId, tender);
    return;
  }
  if (supportsKimdis) {
    await renderKimdisPreview(tender.official_id || tender.display_id || eshidisId, tender);
    return;
  }
  if (!supportsEshidis) {
    $('previewBody').innerHTML = renderTenderExplanation(tender) + `
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
  await renderPreview(actualEshidisId, tender);
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
    await renderKimdisPreview(identifier, tender);
  } else if (String(identifier || '').startsWith('AUTHORITY:')) {
    await renderAuthorityPreview(identifier, tender);
  } else {
    await renderPreview(identifier, tender);
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

async function renderAuthorityPreview(rowKey, tender = {}) {
  const payload = await api(`/api/authority-document-preview?row_key=${encodeURIComponent(rowKey)}`);
  const docs = payload.documents || [];
  const linkedIds = payload.linked_eshidis_ids || [];
  const linkedDocs = payload.linked_eshidis_documents || [];
  const linkedFileCount = Number(payload.linked_eshidis_file_count || 0);
  const explanation = renderTenderExplanation(tender);
  if (!docs.length) {
    $('previewBody').innerHTML = explanation + '<div class="emptyState">Υπάρχουν links εγγράφων στη σελίδα του φορέα. Πάτα Fetch για να κατέβουν τοπικά και μετά ZIP.</div>';
    return;
  }
  const linkedBlock = linkedIds.length
    ? `<div class="docItem linkedBox"><h4>Σύνδεση με ΕΣΗΔΗΣ</h4><p>Βρέθηκε Α/Α ΕΣΗΔΗΣ ${escapeHtml(linkedIds.join(', '))}. ${linkedFileCount ? `Υπάρχουν ήδη ${linkedFileCount} επίσημα αρχεία ΕΣΗΔΗΣ διαθέσιμα για zip.` : 'Το Fetch αυτής της γραμμής θα επιχειρήσει να κατεβάσει και τον επίσημο φάκελο ΕΣΗΔΗΣ.'}</p></div>`
    : `<div class="docItem"><h4>Δεν βρέθηκε ακόμα ΕΣΗΔΗΣ</h4><p>Κρατάμε τη δημοσίευση του φορέα ως υποψήφια. Τα κατεβασμένα έντυπα ελέγχθηκαν για άρθρο 2.2, links και Α/Α ΕΣΗΔΗΣ.</p></div>`;
  const linkedDocuments = linkedDocs.map((doc) => `
    <article class="docItem linkedBox">
      <h4>${escapeHtml(doc.label)}${doc.available ? '' : ' · δεν έχει κατέβει'}</h4>
      <p>${escapeHtml(doc.name || '')}</p>
      <div class="docActions">
        ${doc.view_url ? `<a class="button tinyButton" href="${escapeHtml(doc.view_url)}" target="_blank" rel="noreferrer">Open</a>` : ''}
      </div>
    </article>
  `).join('');
  $('previewBody').innerHTML = explanation + linkedBlock + linkedDocuments + docs.map((doc) => `
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

async function renderKimdisPreview(officialId, tender = {}) {
  const payload = await api(`/api/kimdis-document-preview?official_id=${encodeURIComponent(officialId)}`);
  const docs = payload.documents || [];
  const linkedIds = payload.linked_eshidis_ids || [];
  const linkedDocs = payload.linked_eshidis_documents || [];
  const linkedFileCount = Number(payload.linked_eshidis_file_count || 0);
  const explanation = renderTenderExplanation(tender);
  if (!docs.length) {
    $('previewBody').innerHTML = explanation + '<div class="emptyState">Δεν υπάρχει ακόμα structured ΚΗΜΔΗΣ preview για αυτό το ΑΔΑΜ.</div>';
    return;
  }
  const linkedBlock = linkedIds.length
    ? `<div class="docItem linkedBox"><h4>Σύνδεση με ΕΣΗΔΗΣ</h4><p>Βρέθηκε Α/Α ΕΣΗΔΗΣ ${escapeHtml(linkedIds.join(', '))}. ${linkedFileCount ? `Υπάρχουν ήδη ${linkedFileCount} επίσημα αρχεία ΕΣΗΔΗΣ διαθέσιμα για zip.` : 'Το Fetch αυτής της γραμμής θα επιχειρήσει να κατεβάσει και τον επίσημο φάκελο ΕΣΗΔΗΣ.'}</p></div>`
    : '';
  const linkedDocuments = linkedDocs.map((doc) => `
    <article class="docItem linkedBox">
      <h4>${escapeHtml(doc.label)}${doc.available ? '' : ' · δεν έχει κατέβει'}</h4>
      <p>${escapeHtml(doc.name || '')}</p>
      <div class="docActions">
        ${doc.view_url ? `<a class="button tinyButton" href="${escapeHtml(doc.view_url)}" target="_blank" rel="noreferrer">Open</a>` : ''}
      </div>
    </article>
  `).join('');
  $('previewBody').innerHTML = explanation + linkedBlock + linkedDocuments + docs.map((doc) => `
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

async function renderPreview(eshidisId, tender = {}) {
  const payload = await api(`/api/document-preview?eshidis_id=${encodeURIComponent(eshidisId)}`);
  const docs = payload.documents || [];
  const explanation = renderTenderExplanation(tender);
  if (!docs.length) {
    $('previewBody').innerHTML = explanation + '<div class="emptyState">Δεν υπάρχουν ακόμα συνημμένα στη βάση για αυτό το έργο. Πάτα Fetch official detail και μετά Download files.</div>';
    return;
  }
  $('previewBody').innerHTML = explanation + docs.map((doc) => `
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
    if (path === '/api/discover' && !body?.backfill && finalResult.ok !== false && !finalResult.skipped) {
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
  const sort = $('sortSelect').value || 'deadline_asc';
  const initial = await api('/api/ai-triage', {
    method: 'POST',
    body: JSON.stringify({ scope: 'focus', sort, batch_size: 20 }),
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
  const initial = await api('/api/enrich-candidates', {
    method: 'POST',
    body: JSON.stringify({ scope: 'focus', limit: 50 }),
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
$('forgotPasswordBtn').addEventListener('click', () => requestPasswordReset().catch((error) => { $('loginStatus').textContent = String(error); }));
$('loginPasswordInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') adminLogin().catch((error) => { $('loginStatus').textContent = String(error); });
});
$('refreshBtn').addEventListener('click', refresh);
$('sortSelect').addEventListener('change', () => loadDashboard().catch((error) => { $('statusText').textContent = String(error); }));
$('saveInterestProfileBtn').addEventListener('click', () => saveInterestProfile().catch((error) => { $('interestProfileStatus').textContent = String(error); }));
$('discoverBtn').addEventListener('click', () => {
  const backfill = $('backfillToggle').checked;
  runAction(
    '/api/discover',
    { limit: $('limitInput').value, backfill },
    backfill ? 'Backfill αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ...' : 'Bounded αναζήτηση ΕΣΗΔΗΣ + ΚΗΜΔΗΣ...'
  );
});
$('emailAlertsBtn').addEventListener('click', () => {
  const sort = $('sortSelect').value || 'deadline_asc';
  runAction('/api/email-alerts', { scope: 'focus', sort, dry_run: false }, 'Αποστολή email για νέα έργα...');
});
$('reverseSearchBtn').addEventListener('click', () => runReverseSearch().catch((error) => { $('reverseSearchStatus').textContent = String(error); }));
$('reverseSearchInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') runReverseSearch().catch((error) => { $('reverseSearchStatus').textContent = String(error); });
});
$('pricingIngestActiveBtn').addEventListener('click', () => runPricingActiveIngest().catch((error) => { $('pricingIngestStatus').textContent = String(error); }));
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
$('updateUserRoleBtn').addEventListener('click', () => updateUserRole().catch((error) => { $('roleUpdateStatus').textContent = String(error); }));
$('saveTeeSecretsBtn').addEventListener('click', () => saveTeeSecrets().catch((error) => { $('teeSecretsStatus').textContent = String(error); }));
$('adminRefreshBtn').addEventListener('click', () => loadAdminAudit().catch(() => {}));
$('loadAdminReviewQueueBtn').addEventListener('click', () => {
  $('adminReviewQueueStatus').textContent = 'Φόρτωση false-negative queue...';
  loadAdminAudit('review').catch((error) => { $('adminReviewQueueStatus').textContent = String(error); });
});
$('loadAdminHiddenRowsBtn').addEventListener('click', () => {
  $('adminHiddenRowsStatus').textContent = 'Φόρτωση κρυμμένων έργων...';
  loadAdminAudit('hidden').catch((error) => { $('adminHiddenRowsStatus').textContent = String(error); });
});
$('entalmataRefreshBtn').addEventListener('click', () => loadEntalmata().catch((error) => { $('statusText').textContent = String(error); }));
$('entalmataScanBtn').addEventListener('click', () => runAction('/api/entalmata/scan', {}, 'Σάρωση Διαύγειας για εντάλματα...'));
$('appLogoutBtn').addEventListener('click', () => adminLogout().catch((error) => { $('loginStatus').textContent = String(error); }));
$('appLogoutTopBtn').addEventListener('click', () => adminLogout().catch((error) => { $('loginStatus').textContent = String(error); }));

if (window.location.pathname !== '/password-setup') {
  loadAuthStatus().catch((error) => { $('loginStatus').textContent = String(error); });
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
