from pathlib import Path
from datetime import date
import json
import time

import tender_radar.ui_server as ui_server
from tender_radar.discovery_watermark import append_discovery_run
from tender_radar.ui_server import (
    APP_JS,
    DEFAULT_KIMDIS_DISCOVERY_PAGES,
    INDEX_HTML,
    STYLES_CSS,
    content_type_for_path,
    configured_source_entries,
    dashboard_payload,
    document_zip_bytes,
    email_alerts_payload,
    discovery_search_steps,
    format_budget,
    interest_reason,
    kimdis_document_file_path,
    kimdis_document_preview_payload,
    parse_budget_from_row_text,
    preview_kind,
    quick_source_fingerprint,
    candidate_enrichment_targets,
    run_candidate_enrichment,
    run_ai_triage,
    run_discovery_search,
    run_selected_fetch,
    run_scheduled_poll_and_alert,
    short_text_sample,
    source_polling_payload,
    start_job,
    focus_term_matches,
    url_with_encoded_path,
)


def write_patras_authority_fixture(tmp_path: Path, rows: list[dict]) -> None:
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "work/reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": rows}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_ui_shows_current_version_badge() -> None:
    assert "versionBadge" in INDEX_HTML
    assert "v0.1.14" in INDEX_HTML


def test_ui_exposes_source_polling_audit() -> None:
    assert 'id="sourceAuditSummary"' in INDEX_HTML
    assert 'id="sourceAuditRows"' in INDEX_HTML
    assert "/api/source-polling" in APP_JS
    assert "renderSourcePolling" in APP_JS
    assert "refreshRuntimeViews" in APP_JS


def test_ui_exposes_email_alert_button() -> None:
    assert 'id="emailAlertsBtn"' in INDEX_HTML
    assert "/api/email-alerts" in APP_JS
    assert "Email νέων έργων" in INDEX_HTML


def test_ui_exposes_admin_panel() -> None:
    assert 'data-view="adminPanel"' in INDEX_HTML
    assert 'id="loginScreen"' in INDEX_HTML
    assert 'id="appShell"' in INDEX_HTML
    assert 'id="loginEmailInput"' in INDEX_HTML
    assert 'id="loginPasswordInput"' in INDEX_HTML
    assert 'id="adminHiddenRows"' in INDEX_HTML
    assert 'id="passwordSetupBox"' in INDEX_HTML
    assert 'id="inviteUserBtn"' in INDEX_HTML
    assert "/api/auth/login" in APP_JS
    assert "/api/auth/status" in APP_JS
    assert "/api/auth/logout" in APP_JS
    assert "/api/admin/set-password" in APP_JS
    assert "/api/admin/invite-user" in APP_JS
    assert "/api/admin/users" in APP_JS
    assert "/api/admin/audit" in APP_JS
    assert "/api/admin/restore" in APP_JS


def test_front_page_uses_authenticated_app_shell() -> None:
    assert 'id="loginScreen"' in INDEX_HTML
    assert 'id="appShell" class="appShell" hidden' in INDEX_HTML
    assert "loadAuthStatus" in APP_JS
    assert "if (!state.session && window.location.pathname !== '/password-setup') return;" in APP_JS


def test_tender_table_has_mobile_card_labels() -> None:
    assert 'data-label="Α/Α"' in APP_JS
    assert 'data-label="Πηγή"' in APP_JS
    assert 'data-label="Έργο"' in APP_JS
    assert ".tenderTable thead" in STYLES_CSS
    assert "content: attr(data-label)" in STYLES_CSS


def test_admin_email_code_flow(monkeypatch) -> None:
    sent = {}
    monkeypatch.setattr(ui_server, "email_alert_recipient", lambda: "owner@example.test")
    monkeypatch.setattr(
        ui_server,
        "send_email_alert",
        lambda recipient, subject, text_body, html_body: sent.update(
            {"recipient": recipient, "subject": subject, "text_body": text_body}
        ),
    )
    ui_server.ADMIN_LOGIN_CODES.clear()

    result = ui_server.request_admin_login_code({"email": "owner@example.test"})
    code = ui_server.ADMIN_LOGIN_CODES["owner@example.test"]["code"]

    assert result["ok"] is True
    assert sent["recipient"] == "owner@example.test"
    assert ui_server.verify_admin_login_code(email="owner@example.test", code="000000") is False
    assert ui_server.verify_admin_login_code(email="owner@example.test", code=code) is True
    assert "owner@example.test" not in ui_server.ADMIN_LOGIN_CODES


def test_admin_password_setup_hashes_password(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    sent: list[dict[str, str]] = []

    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(ui_server, "admin_login_email", lambda: "owner@example.test")
    monkeypatch.setattr(
        ui_server,
        "send_email_alert",
        lambda recipient, subject, text_body, html_body: sent.append(
            {"recipient": recipient, "subject": subject, "text": text_body, "html": html_body}
        ),
    )
    monkeypatch.setattr(ui_server.secrets, "token_urlsafe", lambda size=32: "setup-token")

    result = ui_server.request_admin_password_setup({"email": "owner@example.test"}, base_url="https://example.test")
    completed = ui_server.complete_admin_password_setup(token="setup-token", password="long-secure-password")

    user = ui_server.get_admin_user(db_path, "owner@example.test")
    assert result["sent"] is True
    assert sent[0]["recipient"] == "owner@example.test"
    assert "https://example.test/password-setup?token=setup-token" in sent[0]["text"]
    assert completed == {"email": "owner@example.test", "role": "admin"}
    assert user is not None
    assert user.role == "admin"
    assert user.password_hash is not None
    assert "long-secure-password" not in user.password_hash
    assert ui_server.verify_password("long-secure-password", user.password_hash) is True


def test_admin_invite_user_creates_user_role(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    sent: list[str] = []

    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(ui_server, "send_email_alert", lambda recipient, subject, text_body, html_body: sent.append(text_body))
    monkeypatch.setattr(ui_server.secrets, "token_urlsafe", lambda size=32: "invite-token")

    result = ui_server.invite_admin_user(
        {"email": "worker@example.test", "role": "user"},
        inviter="owner@example.test",
        base_url="https://example.test",
    )
    completed = ui_server.complete_admin_password_setup(token="invite-token", password="long-secure-password")
    user = ui_server.get_admin_user(db_path, "worker@example.test")

    assert result["role"] == "user"
    assert "https://example.test/password-setup?token=invite-token" in sent[0]
    assert completed == {"email": "worker@example.test", "role": "user"}
    assert user is not None
    assert user.role == "user"
    assert ui_server.verify_admin_user_password(email="worker@example.test", password="long-secure-password") is False


def test_report_json_content_type_includes_utf8_charset() -> None:
    assert content_type_for_path(Path("candidates.json")) == "application/json; charset=utf-8"


def test_report_markdown_content_type_includes_utf8_charset() -> None:
    assert content_type_for_path(Path("candidates.md")) == "text/markdown; charset=utf-8"


def test_url_with_encoded_path_handles_greek_pdf_names() -> None:
    url = "https://www.dorida.gr/wp-content/uploads/Περίληψη-Διακήρυξης.pdf"

    encoded = url_with_encoded_path(url)

    assert encoded == "https://www.dorida.gr/wp-content/uploads/%CE%A0%CE%B5%CF%81%CE%AF%CE%BB%CE%B7%CF%88%CE%B7-%CE%94%CE%B9%CE%B1%CE%BA%CE%AE%CF%81%CF%85%CE%BE%CE%B7%CF%82.pdf"


def test_ui_has_separate_id_source_columns_and_kimdis_tool_input() -> None:
    assert "<th>Α/Α</th>" in INDEX_HTML
    assert "<th>Πηγή</th>" in INDEX_HTML
    assert "Α/Α / Πηγή" not in INDEX_HTML
    assert 'id="sortSelect"' in INDEX_HTML
    assert "knownTenderCount" not in INDEX_HTML
    assert 'id="kimdisInput"' in INDEX_HTML
    assert 'id="kimdisFetchBtn"' in INDEX_HTML


def test_ui_uses_safer_discovery_defaults() -> None:
    assert 'value="100"' in INDEX_HTML
    steps = discovery_search_steps(limit=100, as_of_date="2026-07-17")
    expanded_args = steps[1]["args"]
    assert expanded_args[expanded_args.index("--kimdis-pages") + 1] == str(DEFAULT_KIMDIS_DISCOVERY_PAGES)
    assert DEFAULT_KIMDIS_DISCOVERY_PAGES == 20


def test_configured_source_entries_include_global_and_authority_sources() -> None:
    config = {
        "global_sources": [{"id": "eshidis_active_search"}, {"id": "khmdhs_notice"}],
        "authority_adapters": [{"id": "epatras_tenders"}],
    }

    entries = configured_source_entries(config)

    assert [entry["id"] for entry in entries] == ["eshidis_active_search", "khmdhs_notice", "epatras_tenders"]
    assert [entry["source_group"] for entry in entries] == [
        "global_sources",
        "global_sources",
        "authority_adapters",
    ]


def test_quick_source_fingerprint_counts_configured_attempted_and_template_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/sources.yml").write_text(
        """
global_sources:
  - id: global_web
    type: web
    url: https://example.test/root
  - id: template
    type: url_template
    url: https://example.test/item/{ID}
authority_adapters:
  - id: authority
    adapter: html_listing
    url: https://example.test/list
""".strip(),
        encoding="utf-8",
    )

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, *_args):
            return b"<html><a href='/tender.pdf'>PDF</a></html>"

    monkeypatch.setattr(ui_server, "urlopen", lambda request, timeout=None: Response())

    result = quick_source_fingerprint(timeout_seconds=1)

    assert result["source_count"] == {
        "configured_total": 3,
        "attempted_total": 2,
        "reached_total": 2,
        "template_total": 1,
        "error_total": 0,
    }


def test_eshidis_active_preflight_uses_cached_candidate_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/sources.yml").write_text(
        """
global_sources:
  - id: eshidis_active_search
    type: web_app
    url: https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/active_search_main.jspx
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "work/reports/eshidis_active_candidates.json").write_text(
        json.dumps(
            {
                "candidate_status": "DISCOVERED_ACTIVE_CANDIDATE",
                "coverage": {"candidates_found": 1},
                "candidates": [
                    {
                        "eshidis_id": "221744",
                        "title": "Συντηρήσεις οδικού δικτύου",
                        "authority": "Δήμος",
                        "submission_deadline": "2026-08-20 10:00",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("ESHIDIS preflight should use cached report instead of opening the web app")

    monkeypatch.setattr(ui_server, "urlopen", fail_urlopen)

    result = quick_source_fingerprint(timeout_seconds=1)
    source = result["sources"][0]

    assert result["source_count"]["attempted_total"] == 1
    assert result["source_count"]["reached_total"] == 1
    assert source["source_id"] == "eshidis_active_search"
    assert source["status"] == "CACHED_DISCOVERY_WATERMARK"
    assert source["attempted"] is False
    assert source["count_hint"] == 1


def test_discovery_preflight_skips_when_only_failed_sources_are_degraded(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text("{}", encoding="utf-8")
    previous_source = {
        "source_id": "source_a",
        "adapter": "html_listing",
        "token": "same",
        "date": "2026-07-18",
        "count_hint": 1,
    }
    previous_sources = [
        previous_source,
        {"source_id": "source_b", "adapter": "html_listing", "token": "old", "date": None, "count_hint": None},
        {"source_id": "source_c", "adapter": "html_listing", "token": "old", "date": None, "count_hint": None},
        {"source_id": "source_d", "adapter": "html_listing", "token": "old", "date": None, "count_hint": None},
    ]
    (tmp_path / "work/derived/source_fingerprints.json").write_text(
        json.dumps({"version": 1, "latest": {"ok": False, "hash": "old", "sources": previous_sources}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ui_server,
        "quick_source_fingerprint",
        lambda timeout_seconds=8: {
            "ok": False,
            "hash": "new",
            "sources": [previous_source],
            "errors": [{"source": "source_b", "message": "timeout"}],
        },
    )

    result = ui_server.discovery_change_preflight()

    assert result["skip"] is True
    assert result["status"] == "SKIPPED_DEGRADED_NO_SUCCESSFUL_SOURCE_CHANGES"
    assert result["changed_source_ids"] == []


def test_source_error_preserves_previous_successful_fingerprint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/sources.yml").write_text(
        """
authority_adapters:
  - id: diavgeia_patras
    adapter: diavgeia_api
    url: https://diavgeia.gov.gr/opendata/search.json
""".strip(),
        encoding="utf-8",
    )
    previous = {
        "ok": True,
        "computed_at": "2026-07-18T10:00:00+00:00",
        "sources": [
            {
                "source_id": "diavgeia_patras",
                "source_group": "authority_adapters",
                "adapter": "diavgeia_api",
                "url": "https://diavgeia.gov.gr/opendata/search.json",
                "attempted": True,
                "reachable": True,
                "token": "stable-ada",
                "date": "2026-07-18",
            }
        ],
        "errors": [],
    }
    current = {
        "ok": False,
        "computed_at": "2026-07-18T11:00:00+00:00",
        "sources": [],
        "errors": [{"source": "diavgeia_patras", "message": "HTTP Error 503"}],
    }

    ui_server.persist_source_preflight_state(current=previous, previous=None)
    ui_server.persist_source_preflight_state(current=current, previous=previous)

    state = ui_server.get_source_state(tmp_path / "data/tender_radar.sqlite", "diavgeia_patras")
    assert state is not None
    assert state.last_status == "ERROR"
    assert state.fingerprint is not None
    assert state.metadata["token"] == "stable-ada"
    assert state.metadata["date"] == "2026-07-18"
    assert state.metadata["reachable"] is False


def test_discovery_preflight_ignores_non_discovery_source_changes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config/sources.yml").write_text(
        """
global_sources:
  - id: eshidis_active_search
    type: web_app
    url: https://example.test/eshidis
  - id: eshidis_tender_page
    type: url_template
    url: https://example.test/{ESHIDIS_ID}
  - id: ted
    type: web
    url: https://example.test/ted
authority_adapters: []
""",
        encoding="utf-8",
    )
    previous_sources = [
        {"source_id": "eshidis_active_search", "adapter": "web_app", "token": "same", "date": None, "count_hint": None},
        {"source_id": "eshidis_tender_page", "adapter": "url_template", "token": "old", "date": None, "count_hint": None},
        {"source_id": "ted", "adapter": "web", "token": "old", "date": None, "count_hint": None},
    ]
    current_sources = [
        {"source_id": "eshidis_active_search", "adapter": "web_app", "token": "same", "date": None, "count_hint": None},
        {"source_id": "eshidis_tender_page", "adapter": "url_template", "token": "new", "date": None, "count_hint": None},
        {"source_id": "ted", "adapter": "web", "token": "new", "date": None, "count_hint": None},
    ]
    (tmp_path / "work/derived/source_fingerprints.json").write_text(
        json.dumps({"version": 1, "latest": {"ok": False, "hash": "old", "sources": previous_sources}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ui_server,
        "quick_source_fingerprint",
        lambda timeout_seconds=8: {
            "ok": False,
            "hash": "new",
            "sources": current_sources,
            "errors": [{"source": "diavgeia", "message": "timeout"}],
        },
    )

    result = ui_server.discovery_change_preflight()

    assert result["skip"] is True
    assert result["changed_source_ids"] == []


def test_latest_source_fingerprint_prefers_latest_degraded_baseline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "work/derived/source_fingerprints.json").write_text(
        json.dumps(
            {
                "version": 1,
                "latest": {"ok": False, "hash": "degraded"},
                "latest_complete": {"ok": True, "hash": "complete"},
            }
        ),
        encoding="utf-8",
    )

    assert ui_server.latest_source_fingerprint() == {"ok": False, "hash": "degraded"}


def test_discovery_preflight_uses_sqlite_source_state_before_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/sources.yml").write_text("authority_adapters: []\n", encoding="utf-8")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text("{}", encoding="utf-8")
    current = {
        "ok": True,
        "computed_at": "2026-07-18T10:00:00+00:00",
        "hash": "global-current",
        "sources": [
            {"source_id": "eshidis_active_search", "adapter": "web_app", "token": "same"},
            {"source_id": "khmdhs_notice", "adapter": "api_post", "token": "same"},
            {"source_id": "khmdhs_auction", "adapter": "api_post", "token": "same"},
            {"source_id": "khmdhs_contract", "adapter": "api_post", "token": "same"},
        ],
        "errors": [],
    }

    ui_server.persist_source_preflight_state(current=current, previous=None)
    monkeypatch.setattr(ui_server, "quick_source_fingerprint", lambda timeout_seconds=8: current)

    result = ui_server.discovery_change_preflight()

    assert result["skip"] is True
    assert result["status"] == "SKIPPED_UNCHANGED"
    assert result["previous_hash"] != current["hash"]
    assert ui_server.latest_source_fingerprint()["state_source"] == "sqlite"


def test_source_polling_payload_reads_sqlite_state_and_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config/sources.yml").write_text(
        """
global_sources:
  - id: eshidis_active_search
    name: ΕΣΗΔΗΣ
    type: web_app
    url: https://example.test/eshidis
  - id: template_source
    name: Template
    type: url_template
    url: https://example.test/{ID}
authority_adapters:
  - id: nafpaktos_tenders
    name: Ναύπακτος
    adapter: html_listing
    url: https://example.test/nafpaktos
""".strip(),
        encoding="utf-8",
    )
    ui_server.upsert_source_state(
        ui_server.runtime_db_path(),
        source_id="eshidis_active_search",
        source_family="web_app",
        source_url="https://example.test/eshidis",
        fingerprint="a",
        checked_at="2026-07-18T10:00:00+00:00",
        status="CHANGED",
        metadata={"adapter": "web_app", "source_group": "global_sources", "reachable": True},
    )
    ui_server.upsert_source_state(
        ui_server.runtime_db_path(),
        source_id="nafpaktos_tenders",
        source_family="html_listing",
        source_url="https://example.test/nafpaktos",
        fingerprint="b",
        checked_at="2026-07-18T10:01:00+00:00",
        status="ERROR",
        error="timeout",
        metadata={"adapter": "html_listing", "source_group": "authority_adapters", "reachable": False},
    )

    payload = source_polling_payload()

    assert payload["summary"]["configured_total"] == 3
    assert payload["summary"]["tracked_total"] == 2
    assert payload["summary"]["changed_total"] == 1
    assert payload["summary"]["selective_changed_total"] == 1
    assert payload["summary"]["error_total"] == 1
    assert payload["summary"]["selective_error_total"] == 1
    assert payload["summary"]["never_checked_total"] == 1
    by_id = {row["source_id"]: row for row in payload["rows"]}
    assert by_id["eshidis_active_search"]["selective_refresh_capable"] is True
    assert by_id["nafpaktos_tenders"]["last_error"] == "timeout"
    assert by_id["template_source"]["last_status"] == "NEVER_CHECKED"


def test_email_alerts_payload_skips_rows_already_sent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(ui_server, "email_alert_recipient", lambda: "owner@example.test")
    monkeypatch.setattr(
        ui_server,
        "dashboard_payload",
        lambda scope="focus", sort="deadline_asc": {
            "summary": {"visible": 2},
            "tenders": [
                {
                    "row_key": "ESHIDIS:221744",
                    "display_id": "221744",
                    "source_label": "ΕΣΗΔΗΣ",
                    "eshidis_id": "221744",
                    "title": "Συντηρήσεις οδικού δικτύου",
                    "authority_name": "Δήμος Αμφιλοχίας",
                    "budget_display": "1.000.000",
                    "deadline_display": "2026-08-07 10:00",
                },
                {
                    "row_key": "KIMDIS:26PROC000000001",
                    "display_id": "26PROC000000001",
                    "source_label": "ΚΗΜΔΗΣ",
                    "official_url": "https://example.test/notice",
                    "title": "Αναπλάσεις",
                    "authority_name": "Δήμος Ναυπακτίας",
                    "budget_display": "500.000",
                    "deadline_display": "2026-08-10",
                },
            ],
        },
    )
    ui_server.record_notification_sent(
        ui_server.runtime_db_path(),
        row_key="ESHIDIS:221744",
        channel="email",
        recipient="owner@example.test",
        subject="old",
    )

    payload = email_alerts_payload(dry_run=True)

    assert payload["candidate_rows"] == 2
    assert payload["new_count"] == 1
    assert payload["skipped_already_sent"] == 1
    assert payload["new_rows"][0]["row_key"] == "KIMDIS:26PROC000000001"
    assert payload["skipped_rows"][0]["row_key"] == "ESHIDIS:221744"
    assert "https://example.test/notice" in payload["text_body"]


def test_scheduled_poll_and_alert_writes_audit_reports(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(
        ui_server,
        "run_discovery_search",
        lambda limit, backfill=False: {
            "ok": True,
            "skipped": True,
            "source_preflight": {"changed_source_ids": ["nafpaktos_tenders"]},
            "steps": [],
            "dashboard": {"summary": {"visible": 1}},
        },
    )
    monkeypatch.setattr(
        ui_server,
        "run_incremental_ai_triage",
        lambda scope="focus", sort="deadline_asc", batch_size=20: {"ok": True, "summary": {"rows": 1}},
    )
    monkeypatch.setattr(
        ui_server,
        "run_candidate_enrichment",
        lambda scope="focus", limit=50, **kwargs: {"ok": True, "summary": {"attempted": 0}},
    )
    monkeypatch.setattr(
        ui_server,
        "run_email_alerts",
        lambda scope="focus", sort="deadline_asc", recipient=None, dry_run=False: {
            "ok": True,
            "dry_run": dry_run,
            "recipient": recipient,
            "candidate_rows": 1,
            "new_count": 1,
            "skipped_already_sent": 0,
            "sent": 0,
        },
    )
    monkeypatch.setattr(
        ui_server,
        "source_polling_payload",
        lambda: {
            "summary": {
                "configured_total": 31,
                "selective_capable_total": 25,
                "changed_total": 1,
                "selective_changed_total": 1,
                "unchanged_total": 30,
                "error_total": 0,
            },
            "rows": [
                {"source_id": "nafpaktos_tenders", "last_status": "CHANGED"},
                {"source_id": "thermo_wp", "last_status": "SKIPPED_UNCHANGED"},
            ],
        },
    )
    report = tmp_path / "work/reports/scheduled.json"
    markdown = tmp_path / "work/reports/scheduled.md"

    payload = run_scheduled_poll_and_alert(
        recipient="owner@example.test",
        dry_run=True,
        report_path=report,
        markdown_report_path=markdown,
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["changed_source_ids"] == ["nafpaktos_tenders"]
    assert payload["skipped_sources"] == ["thermo_wp"]
    assert payload["email"]["new_count"] == 1
    assert report.exists()
    assert markdown.exists()
    assert "Scheduled Poll and Alert" in markdown.read_text(encoding="utf-8")


def test_scheduled_poll_skips_ai_when_all_rows_already_triaged(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "work/reports").mkdir(parents=True)
    dashboard_row = {"row_key": "AUTHORITY:AUTH-1", "title": "Δημοτική οδοποιία"}
    (tmp_path / "work/reports/ai_triage_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_key": "AUTHORITY:AUTH-1",
                        "triage_signature": ui_server.ai_triage_signature(dashboard_row),
                        "ai": {
                            "decision": "KEEP_ACTIVE_TENDER",
                            "keep_for_daily_review": True,
                            "confidence": 0.8,
                            "reason": "already checked",
                            "eshidis_id_candidates": [],
                        },
                    }
                ],
                "summary": {"errors": 0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ui_server,
        "dashboard_payload",
        lambda scope="focus", sort="deadline_asc", apply_triage=True: {
            "summary": {"visible": 1},
            "tenders": [dashboard_row],
        },
    )
    monkeypatch.setattr(ui_server, "ai_triage_report_status", lambda: {"exists": True, "ok": True})

    def fail_build_report(*args, **kwargs):
        raise AssertionError("scheduler should not call OpenAI when no row is pending")

    monkeypatch.setattr("tender_radar.ai_triage.build_ai_triage_report", fail_build_report)

    result = ui_server.run_incremental_ai_triage(scope="focus", sort="deadline_asc", batch_size=5)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["skip_reason"] == "NO_PENDING_AI_TRIAGE_ROWS"
    assert result["summary"]["kept_total"] == 1


def test_incremental_ai_triage_rechecks_stale_cached_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/reports/ai_triage_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_key": "AUTHORITY:AUTH-1",
                        "triage_signature": "old-signature",
                        "ai": {
                            "decision": "DROP_NOT_PUBLIC_WORKS",
                            "keep_for_daily_review": False,
                            "confidence": 0.8,
                            "reason": "old cached result",
                            "eshidis_id_candidates": [],
                        },
                    }
                ],
                "summary": {"errors": 0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ui_server,
        "dashboard_payload",
        lambda scope="focus", sort="deadline_asc", apply_triage=True: {
            "summary": {"visible": 1},
            "tenders": [{"row_key": "AUTHORITY:AUTH-1", "title": "Δημοτική οδοποιία"}],
        },
    )
    monkeypatch.setattr(ui_server, "ai_triage_report_status", lambda: {"exists": True, "ok": True})
    captured = {}

    def fake_build_report(rows, **kwargs):
        captured["rows"] = rows
        return {
            "model": "fake",
            "rows": [
                {
                    "row_key": "AUTHORITY:AUTH-1",
                    "ai": {
                        "decision": "KEEP_ACTIVE_TENDER",
                        "keep_for_daily_review": True,
                        "confidence": 0.9,
                        "reason": "fresh row was rechecked",
                        "eshidis_id_candidates": [],
                    },
                }
            ],
            "errors": [],
            "safety_note": "test",
        }

    monkeypatch.setattr("tender_radar.ai_triage.build_ai_triage_report", fake_build_report)

    result = ui_server.run_incremental_ai_triage(scope="focus", sort="deadline_asc", batch_size=5)

    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["pending_rows"] == 1
    assert captured["rows"][0]["triage_signature"] != "old-signature"


def test_incremental_ai_triage_includes_fetched_ocr_document_text(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "work/reports").mkdir(parents=True)
    text_path = tmp_path / "work/extracted_text/authority/auth_work_0.txt"
    text_path.parent.mkdir(parents=True)
    text_path.write_text(
        "ΔΙΑΚΗΡΥΞΗ ΕΡΓΟΥ άρθρο 2.2 Διεύθυνση εγγράφων σύμβασης "
        "https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/217922 "
        "Ε.Σ.Η.Δ.Η.Σ Α/Α Διαγωνισμού 217922",
        encoding="utf-8",
    )
    ui_server.upsert_source_document(
        ui_server.runtime_db_path(),
        row_key="AUTHORITY:AUTH-work",
        document_url="https://example.test/declaration.pdf",
        source_url="https://example.test/work",
        local_path=str(tmp_path / "work/download_audit/authority/declaration.pdf"),
        metadata={
            "text_path": str(text_path),
            "document_analysis": {
                "document_type": "tender_declaration",
                "extraction_status": "TEXT_EXTRACTED_WITH_OCR",
                "ocr_status": "OCR_TEXT_EXTRACTED",
            },
        },
    )
    monkeypatch.setattr(
        ui_server,
        "dashboard_payload",
        lambda scope="focus", sort="deadline_asc", apply_triage=True: {
            "summary": {"visible": 1},
            "tenders": [
                {
                    "row_key": "AUTHORITY:AUTH-work",
                    "display_id": "AUTH-work",
                    "source_label": "Φορέας",
                    "title": "Διακήρυξη έργου οδοποιίας",
                    "authority_name": "Δήμος Δωρίδος",
                    "supports_authority_actions": True,
                }
            ],
        },
    )
    captured = {}

    def fake_build_report(rows, **kwargs):
        captured["rows"] = rows
        return {
            "model": "fake",
            "rows": [
                {
                    "row_key": "AUTHORITY:AUTH-work",
                    "ai": {
                        "decision": "KEEP_ACTIVE_TENDER",
                        "keep_for_daily_review": True,
                        "confidence": 0.95,
                        "reason": "OCR declaration contains ESHIDIS link.",
                        "eshidis_id_candidates": rows[0]["linked_eshidis_ids"],
                    },
                }
            ],
            "errors": [],
            "safety_note": "test",
        }

    monkeypatch.setattr("tender_radar.ai_triage.build_ai_triage_report", fake_build_report)

    result = ui_server.run_incremental_ai_triage(scope="focus", sort="deadline_asc", batch_size=5)

    assert result["ok"] is True
    row = captured["rows"][0]
    assert row["linked_eshidis_ids"] == ["217922"]
    assert row["document_evidence_count"] == 1
    assert row["document_evidence"][0]["ocr_status"] == "OCR_TEXT_EXTRACTED"
    assert "217922" in " ".join(row["document_evidence"][0]["snippets"])


def test_candidate_enrichment_uses_ai_eshidis_id_before_refetching_authority(monkeypatch) -> None:
    row = {
        "row_key": "AUTHORITY:AUTH-work",
        "official_id": "AUTH-work",
        "supports_authority_actions": True,
        "ai_triage": {"eshidis_id_candidates": ["217922"]},
    }

    assert ui_server.candidate_enrichment_identifier(row) == "217922"


def test_scheduled_poll_skips_auto_document_fetch_when_discovery_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    calls = []
    monkeypatch.setattr(
        ui_server,
        "run_discovery_search",
        lambda limit, backfill=False: {
            "ok": True,
            "skipped": True,
            "source_preflight": {"changed_source_ids": []},
            "steps": [],
            "dashboard": {"summary": {"visible": 1}},
        },
    )
    monkeypatch.setattr(
        ui_server,
        "run_incremental_ai_triage",
        lambda scope="focus", sort="deadline_asc", batch_size=20: {"ok": True, "skipped": True},
    )

    def fail_auto_document_fetch(*args, **kwargs):
        raise AssertionError("scheduler should not process old fetch targets when discovery was skipped")

    def fake_email(*args, **kwargs):
        calls.append("email")
        return {
            "ok": True,
            "dry_run": kwargs.get("dry_run"),
            "recipient": kwargs.get("recipient"),
            "candidate_rows": 1,
            "new_count": 1,
            "skipped_already_sent": 0,
            "sent": 0,
        }

    monkeypatch.setattr(ui_server, "run_auto_document_fetch", fail_auto_document_fetch)
    monkeypatch.setattr(
        ui_server,
        "run_email_alerts",
        fake_email,
    )
    monkeypatch.setattr(
        ui_server,
        "source_polling_payload",
        lambda: {"summary": {}, "rows": [{"source_id": "eshidis_active_search", "last_status": "SKIPPED_UNCHANGED"}]},
    )

    payload = run_scheduled_poll_and_alert(dry_run=True)

    assert payload["ok"] is True
    assert calls == ["email"]
    assert payload["auto_document_fetch"]["skipped"] is True
    assert payload["auto_document_fetch"]["summary"] == {}
    assert payload["auto_document_fetch"]["error"] is None
    assert payload["enrichment"] == payload["auto_document_fetch"]


def test_scheduled_poll_treats_auto_document_fetch_failure_as_warning(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(
        ui_server,
        "run_discovery_search",
        lambda limit, backfill=False: {"ok": True, "skipped": False, "source_preflight": {}, "steps": []},
    )
    monkeypatch.setattr(
        ui_server,
        "run_incremental_ai_triage",
        lambda scope="focus", sort="deadline_asc", batch_size=20: {"ok": True, "skipped": True},
    )
    monkeypatch.setattr(
        ui_server,
        "run_auto_document_fetch",
        lambda scope="focus", limit=50: {
            "ok": False,
            "summary": {"attempted": 1, "failed": 1, "stopped_by_time_budget": True},
        },
    )
    monkeypatch.setattr(
        ui_server,
        "run_email_alerts",
        lambda scope="focus", sort="deadline_asc", recipient=None, dry_run=False: {
            "ok": True,
            "dry_run": dry_run,
            "recipient": recipient,
            "candidate_rows": 1,
            "new_count": 0,
            "skipped_already_sent": 1,
            "sent": 0,
        },
    )
    monkeypatch.setattr(ui_server, "source_polling_payload", lambda: {"summary": {}, "rows": []})

    payload = run_scheduled_poll_and_alert(dry_run=True)

    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == [{"stage": "auto_document_fetch", "message": "automatic document fetch failed"}]
    assert payload["email"]["ok"] is True


def test_ui_labels_bounded_and_backfill_discovery_modes() -> None:
    assert "Η γρήγορη αναζήτηση είναι bounded" in INDEX_HTML
    assert 'id="backfillToggle"' in INDEX_HTML
    assert "Backfill safety" in INDEX_HTML
    assert "discoverySafetyText" in APP_JS


def test_dashboard_actions_use_fetch_and_zip_not_preview_buttons() -> None:
    assert "fetchTender" in APP_JS
    assert "/api/fetch-selected" in APP_JS
    assert "/api/document-zip" in APP_JS
    assert "preferredEshidis" in APP_JS
    assert "dismissTender" in APP_JS
    assert "Δεν με ενδιαφέρει" in APP_JS
    assert "previewTender" not in APP_JS


def test_dashboard_rows_select_preview_on_click() -> None:
    assert "selectedRow" in APP_JS
    assert "highlightSelectedRow" in APP_JS
    assert "row.addEventListener('click', () => selectTender(row.dataset.key, false))" in APP_JS
    assert "event.stopPropagation()" in APP_JS


def test_dashboard_includes_authority_candidates_and_actions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-d448a0b21a42080a",
                        "title": "Έργο Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/tender",
                        "attachment_url": "https://e-patras.gr/sites/default/files/a.pdf",
                        "attachment_urls": ["https://e-patras.gr/sites/default/files/a.pdf"],
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": ["e-Patras: PARSED"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus")

    assert payload["summary"]["visible"] == 1
    row = payload["tenders"][0]
    assert row["source_label"] == "Φορέας"
    assert row["supports_authority_actions"] is True
    assert row["supports_eshidis_actions"] is False
    assert row["row_key"] == "AUTHORITY:AUTH-d448a0b21a42080a"
    assert row["attachment_urls"] == ["https://e-patras.gr/sites/default/files/a.pdf"]


def test_long_actions_use_background_job_polling() -> None:
    assert "/api/jobs/" in APP_JS
    assert "sleep(5000)" in APP_JS
    assert "pollJob" in APP_JS


def test_background_job_completes_with_result() -> None:
    started = start_job("unit-test", lambda: {"ok": True, "value": 7})
    job_id = started["job_id"]

    deadline = time.time() + 2
    job = ui_server.job_payload(job_id)
    while job and job["status"] == "running" and time.time() < deadline:
        time.sleep(0.01)
        job = ui_server.job_payload(job_id)

    assert job is not None
    assert job["status"] == "completed"
    assert job["result"] == {"ok": True, "value": 7}


def test_budget_parser_extracts_candidate_row_budget() -> None:
    row_text = "221744 Τίτλος Τακτικός Προϋπολογισμός/ 2.500.000,00 15-07-2026 10:00:00"

    assert parse_budget_from_row_text(row_text) == 2500000.0
    assert format_budget(2500000) == "2.500.000,00 EUR"


def test_dashboard_includes_kimdis_expanded_open_proc_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        """
{
  "summary": {"focus_open_proc_candidates": 2},
  "focus_open_proc_candidates": [
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000001",
      "title": "Έργο στην Πάτρα",
      "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
      "budget": "1240.0",
      "submission_deadline": "2026-07-24T13:00:00",
      "source_url": "https://example.test/notice",
      "attachment_url": "https://example.test/attachment/26PROC000000001",
      "matched_scopes": ["Δήμος Πατρέων"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    },
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000002",
      "title": "Άλλο έργο Πατρών",
      "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
      "budget": "2000.0",
      "submission_deadline": "2026-07-25T10:00:00",
      "source_url": "https://example.test/notice",
      "attachment_url": "https://example.test/attachment/26PROC000000002",
      "matched_scopes": ["Δήμος Πατρέων"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    }
  ]
}
""",
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus")

    assert payload["summary"]["total_known"] == 2
    assert payload["summary"]["visible"] == 2
    assert payload["summary"]["focus_matches"] == 2
    assert payload["tenders"][0]["source_label"] == "ΚΗΜΔΗΣ"
    assert payload["tenders"][0]["display_id"] == "26PROC000000001"
    assert payload["tenders"][0]["interest_reason"] == "Δήμος Πατρέων"
    assert payload["tenders"][0]["download_url"] == "https://example.test/attachment/26PROC000000001"
    assert payload["tenders"][0]["supports_eshidis_actions"] is False
    assert payload["tenders"][0]["deadline_display"] == "24-07-2026 13:00"


def test_dashboard_hides_kimdis_duplicate_when_linked_eshidis_row_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: amfilochia
    name: "Δήμος Αμφιλοχίας"
    aliases: ["Αμφιλοχίας"]
    nuts: ["EL631"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/eshidis_active_candidates.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "eshidis_id": "221744",
                        "title": "ΣΥΝΤΗΡΗΣΕΙΣ ΑΓΡΙΝΙΟΥ ΑΜΦΙΛΟΧΙΑΣ 2026-2027",
                        "authority_name": "ΔΗΜΟΣ ΑΜΦΙΛΟΧΙΑΣ",
                        "submission_deadline": "2026-08-20T10:00:00",
                        "status": "DISCOVERED_ACTIVE_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_open_proc_candidates": [
                    {
                        "source": "KIMDIS",
                        "record_type": "PROC",
                        "official_id": "26PROC019444361",
                        "title": "ΣΥΝΤΗΡΗΣΕΙΣ ΕΠΑΡΧΙΑΚΟΥ ΟΔΙΚΟΥ ΔΙΚΤΥΟΥ Δ. ΑΓΡΙΝΙΟΥ ΚΑΙ Δ. ΑΜΦΙΛΟΧΙΑΣ",
                        "authority": "ΠΕΡΙΦΕΡΕΙΑ ΔΥΤΙΚΗΣ ΕΛΛΑΔΑΣ",
                        "submission_deadline": "2026-08-20T10:00:00",
                        "matched_scopes": ["Δήμος Αμφιλοχίας"],
                        "status": "SUBMISSION_OPEN_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "work/derived/kimdis_open_proc_documents.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "official_id": "26PROC019444361",
                        "linked_eshidis_ids": ["221744"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus", as_of=date(2026, 7, 18))

    assert payload["summary"]["total_known"] == 2
    assert payload["summary"]["duplicate_hidden"] == 1
    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["source_label"] == "ΕΣΗΔΗΣ"
    assert payload["tenders"][0]["display_id"] == "221744"


def test_dashboard_hides_authority_duplicate_when_linked_eshidis_row_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-1234567890abcdef",
                        "title": "Διακήρυξη έργου Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/work",
                        "attachment_urls": ["https://e-patras.gr/work.pdf"],
                        "row_text": "Άρθρο 2.2 resources/search/221473",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "work/derived/authority_documents.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "row_key": "AUTHORITY:AUTH-1234567890abcdef",
                        "linked_eshidis_ids": ["221473"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    import sqlite3

    connection = sqlite3.connect(tmp_path / "data/tender_radar.sqlite")
    try:
        connection.executescript(
            """
            CREATE TABLE tenders (
              id INTEGER PRIMARY KEY,
              eshidis_id TEXT,
              title TEXT,
              authority_name TEXT,
              region TEXT,
              budget_with_vat REAL,
              current_deadline_at TEXT,
              status TEXT,
              status_confidence REAL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO tenders (
              id, eshidis_id, title, authority_name, region,
              budget_with_vat, current_deadline_at, status, status_confidence
            ) VALUES (1, '221473', 'Official ΕΣΗΔΗΣ Πατρών', 'ΔΗΜΟΣ ΠΑΤΡΕΩΝ', NULL, NULL, '2026-08-20T10:00:00', 'UNKNOWN', 0.0)
            """
        )
        connection.commit()
    finally:
        connection.close()

    payload = dashboard_payload(scope="focus", as_of=date(2026, 7, 18))

    assert payload["summary"]["total_known"] == 2
    assert payload["summary"]["duplicate_hidden"] == 1
    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["source_label"] == "ΕΣΗΔΗΣ"
    assert payload["tenders"][0]["display_id"] == "221473"
    assert payload["tenders"][0]["title"] == "Official ΕΣΗΔΗΣ Πατρών"


def test_authority_row_uses_linked_eshidis_ids_from_downloaded_documents(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: dorida
    name: "Δήμος Δωρίδος"
    aliases: ["Ευπάλιο"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-abcdef1234567890",
                        "title": "ΔΗΜΟΤΙΚΗ ΟΔΟΠΟΙΙΑ Δ.Ε. ΕΥΠΑΛΙΟΥ",
                        "authority": "Δήμος Δωρίδος / Ευπάλιο",
                        "source_url": "https://www.dorida.gr/blog/13778/work",
                        "attachment_urls": ["https://www.dorida.gr/wp-content/uploads/Περίληψη.pdf"],
                        "matched_scopes": ["Δήμος Δωρίδος / Ευπάλιο"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "work/derived/authority_documents.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "row_key": "AUTHORITY:AUTH-abcdef1234567890",
                        "original_filename": "Περίληψη.pdf",
                        "linked_eshidis_ids": ["217922"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus")
    row = payload["tenders"][0]

    assert row is not None
    assert row["linked_eshidis_ids"] == ["217922"]
    assert row["official_status_label"] == "Σύνδεση με ΕΣΗΔΗΣ"


def test_discovery_search_fetches_missing_linked_eshidis_after_expanded_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/eshidis_active_candidates.json").write_text('{"candidates": []}', encoding="utf-8")
    monkeypatch.setattr(
        ui_server,
        "discovery_change_preflight",
        lambda: {
            "skip": False,
            "current": {"ok": True},
            "changed_source_ids": ["epatras_tenders"],
            "previous_hash": "old",
        },
    )
    monkeypatch.setattr(ui_server, "latest_successful_discovery_run", lambda path: None)
    monkeypatch.setattr(ui_server, "save_source_fingerprint", lambda fingerprint: None)
    monkeypatch.setattr(
        ui_server,
        "record_discovery_pass",
        lambda **kwargs: {"success": True, "watermark": {"complete": True}},
    )
    calls = []

    def fake_run_cli_process(args, *, timeout):
        calls.append(args)
        if args[:2] == ["sources", "expanded-report"]:
            (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
                json.dumps(
                    {
                        "focus_authority_candidates": [
                            {
                                "source": "AUTHORITY",
                                "record_type": "AUTHORITY_WEB",
                                "official_id": "AUTH-1234567890abcdef",
                                "title": "Διακήρυξη έργου Δήμου Πατρέων",
                                "authority": "Δήμος Πατρέων",
                                "source_url": "https://e-patras.gr/el/work",
                                "attachment_urls": ["https://e-patras.gr/work.pdf"],
                                "row_text": "Άρθρο 2.2 resources/search/221473",
                                "matched_scopes": ["Δήμος Πατρέων"],
                                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "command": " ".join(args), "stdout": "{}", "stderr": ""}

    monkeypatch.setattr(ui_server, "run_cli_process", fake_run_cli_process)

    result = ui_server.run_discovery_search(limit=25)

    names = [step["name"] for step in result["steps"]]
    assert "fetch_detail_221473" in names
    assert "download_files_221473" in names
    assert ["sources", "fetch-resource", "221473", "--allow-insecure-tls"] in calls


def test_dashboard_can_sort_by_budget_desc(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        """
{
  "focus_open_proc_candidates": [
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000001",
      "title": "Μικρό έργο Πατρών",
      "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
      "budget": "1000.0",
      "submission_deadline": "2026-07-24T13:00:00",
      "matched_scopes": ["Δήμος Πατρέων"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    },
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000002",
      "title": "Μεγάλο έργο Πατρών",
      "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
      "budget": "9000.0",
      "submission_deadline": "2026-07-25T10:00:00",
      "matched_scopes": ["Δήμος Πατρέων"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    }
  ]
}
""",
        encoding="utf-8",
    )

    by_deadline = dashboard_payload(scope="focus", sort="deadline_asc", as_of=date(2026, 7, 18))
    by_budget = dashboard_payload(scope="focus", sort="budget_desc", as_of=date(2026, 7, 18))

    assert [row["display_id"] for row in by_deadline["tenders"]] == ["26PROC000000001", "26PROC000000002"]
    assert [row["display_id"] for row in by_budget["tenders"]] == ["26PROC000000002", "26PROC000000001"]


def test_dashboard_hides_parseable_expired_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        """
{
  "focus_open_proc_candidates": [
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000001",
      "title": "Ληγμένο έργο Πατρών",
      "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
      "submission_deadline": "2026-07-17T13:00:00",
      "matched_scopes": ["Δήμος Πατρέων"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    },
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000002",
      "title": "Ενεργό έργο Πατρών",
      "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
      "submission_deadline": "2026-07-19T10:00:00",
      "matched_scopes": ["Δήμος Πατρέων"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    }
  ]
}
""",
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus", as_of=date(2026, 7, 18))

    assert payload["summary"]["total_known"] == 2
    assert payload["summary"]["visible"] == 1
    assert payload["summary"]["expired_hidden"] == 1
    assert payload["tenders"][0]["display_id"] == "26PROC000000002"


def test_dashboard_exposes_local_kimdis_preview_and_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    pdf_path = tmp_path / "work/download_audit/kimdis/26PROC000000001/26PROC000000001.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF")
    linked_pdf_path = tmp_path / "work/download_audit/eshidis/221473/spec.pdf"
    linked_pdf_path.parent.mkdir(parents=True)
    linked_pdf_path.write_bytes(b"%PDF")
    import sqlite3

    db_path = tmp_path / "data/tender_radar.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE tenders (
              id INTEGER PRIMARY KEY,
              eshidis_id TEXT,
              title TEXT,
              authority_name TEXT,
              region TEXT,
              budget_with_vat REAL,
              current_deadline_at TEXT,
              status TEXT,
              status_confidence REAL
            );
            CREATE TABLE attachments (
              id INTEGER PRIMARY KEY,
              tender_id INTEGER,
              original_name TEXT,
              local_path TEXT,
              is_latest INTEGER
            );
            """
        )
        connection.execute(
            """
            INSERT INTO tenders (
              id, eshidis_id, title, authority_name, region,
              budget_with_vat, current_deadline_at, status, status_confidence
            ) VALUES (1, '221473', 'Linked ΕΣΗΔΗΣ', 'ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ', NULL, NULL, NULL, 'UNKNOWN', 0.0)
            """
        )
        connection.execute(
            "INSERT INTO attachments (tender_id, original_name, local_path, is_latest) VALUES (1, 'spec.pdf', ?, 1)",
            (str(linked_pdf_path.relative_to(tmp_path)),),
        )
        connection.commit()
    finally:
        connection.close()
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: nafpaktia
    name: "Δήμος Ναυπακτίας"
    aliases: ["Ναυπακτία"]
    nuts: ["EL631"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        """
{
  "focus_open_proc_candidates": [
    {
      "source": "KIMDIS",
      "record_type": "PROC",
      "official_id": "26PROC000000001",
      "title": "Έργο Ναυπακτίας",
      "authority": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ",
      "budget": "1000.0",
      "submission_deadline": "2026-08-01T10:00:00",
      "source_url": "https://example.test/notice",
      "attachment_url": "https://example.test/attachment/26PROC000000001",
      "matched_scopes": ["Δήμος Ναυπακτίας"],
      "status": "SUBMISSION_OPEN_CANDIDATE"
    }
  ]
}
""",
        encoding="utf-8",
    )
    (tmp_path / "work/derived/kimdis_open_proc_documents.json").write_text(
        f"""
{{
  "documents": [
    {{
      "official_id": "26PROC000000001",
      "candidate_status": "SUBMISSION_OPEN_CANDIDATE",
      "verification_status": "ATTACHMENT_ALREADY_FETCHED_PENDING_DOCUMENT_REVIEW",
      "local_path": "{pdf_path.relative_to(tmp_path)}",
      "original_filename": "26PROC000000001.pdf",
      "size_bytes": 4,
      "sha256": "abc",
      "linked_eshidis_ids": ["221473"],
      "attachment_url": "https://example.test/attachment/26PROC000000001",
      "document_analysis": {{"document_type": "tender_declaration", "text_sample": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ"}},
      "document_evidence": {{"evidence_status": "DOCUMENT_EVIDENCE_FOUND", "authority_match": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ", "scope_alias_matches": ["Δήμος Ναυπακτίας"]}}
    }}
  ]
}}
""",
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus")
    preview = kimdis_document_preview_payload("26PROC000000001")
    file_path = kimdis_document_file_path("26PROC000000001")

    assert payload["tenders"][0]["supports_kimdis_actions"] is True
    assert payload["tenders"][0]["download_url"] == "/api/kimdis-document-file?official_id=26PROC000000001"
    assert payload["tenders"][0]["preview_url"] == "/api/kimdis-document-preview?official_id=26PROC000000001"
    assert payload["tenders"][0]["linked_eshidis_ids"] == ["221473"]
    assert preview["linked_eshidis_ids"] == ["221473"]
    assert preview["linked_eshidis_file_count"] == 1
    assert preview["documents"][0]["label"] == "Διακήρυξη"
    assert preview["documents"][0]["view_url"] == "/api/kimdis-document-file?official_id=26PROC000000001"
    assert file_path == pdf_path.resolve()


def test_selected_kimdis_fetch_chains_linked_eshidis_download(monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "run_kimdis_fetch", lambda official_id: {"ok": True, "official_id": official_id})
    monkeypatch.setattr(ui_server, "kimdis_linked_eshidis_ids", lambda official_id: ["221473"])
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}})

    captured = {}

    def fake_run_cli_steps(steps, *, dashboard_scope=None):
        captured["steps"] = steps
        captured["dashboard_scope"] = dashboard_scope
        return {"ok": True, "steps": steps, "dashboard": {"scope": dashboard_scope}}

    monkeypatch.setattr(ui_server, "run_cli_steps", fake_run_cli_steps)

    result = run_selected_fetch("26PROC019417347")

    assert result["ok"] is True
    assert result["linked_eshidis_ids"] == ["221473"]
    assert captured["dashboard_scope"] == "focus"
    assert [step["name"] for step in captured["steps"]] == ["fetch_detail_221473", "download_files_221473"]
    assert captured["steps"][0]["args"] == ["sources", "fetch-resource", "221473", "--allow-insecure-tls"]


def test_candidate_enrichment_targets_only_visible_non_eshidis_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: nafpaktia
    name: "Δήμος Ναυπακτίας"
    aliases: ["Ναύπακτος"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/eshidis_active_candidates.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "eshidis_id": "221473",
                        "title": "Έργο Ναυπάκτου",
                        "authority_name": "Δήμος Ναυπακτίας",
                        "submission_deadline": "20-08-2026 10:00:00",
                        "row_text": "Ναύπακτος",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_open_proc_candidates": [
                    {
                        "official_id": "26PROC000000001",
                        "title": "Διακήρυξη έργου Ναυπάκτου",
                        "authority": "Δήμος Ναυπακτίας",
                        "attachment_url": "https://example.test/26PROC000000001.pdf",
                        "matched_scopes": ["Δήμος Ναυπακτίας"],
                        "status": "SUBMISSION_OPEN_CANDIDATE",
                    }
                ],
                "focus_authority_candidates": [
                    {
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-work",
                        "title": "Περίληψη έργου Ναυπάκτου",
                        "authority": "Δήμος Ναυπακτίας",
                        "source_url": "https://example.test/work",
                        "attachment_url": "https://example.test/work.pdf",
                        "attachment_urls": ["https://example.test/work.pdf"],
                        "matched_scopes": ["Δήμος Ναυπακτίας"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    targets, skipped = candidate_enrichment_targets(scope="focus", limit=10)

    assert skipped == 0
    assert sorted(target["identifier"] for target in targets) == ["26PROC000000001", "AUTHORITY:AUTH-work"]


def test_candidate_enrichment_uses_selected_fetch_and_records_attempts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(
        ui_server,
        "candidate_enrichment_targets",
        lambda scope, limit: (
            [
                {
                    "row_key": "KIMDIS:26PROC000000001",
                    "identifier": "26PROC000000001",
                    "kind": "ΚΗΜΔΗΣ",
                    "source_signature": "sig-1",
                },
                {
                    "row_key": "AUTHORITY:AUTH-work",
                    "identifier": "AUTHORITY:AUTH-work",
                    "kind": "Φορέας",
                    "source_signature": "sig-2",
                },
            ],
            0,
        ),
    )

    def fake_selected_fetch(identifier):
        calls.append(identifier)
        return {"ok": True, "linked_eshidis_ids": ["221473"] if identifier.startswith("26PROC") else []}

    monkeypatch.setattr(ui_server, "run_selected_fetch", fake_selected_fetch)
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}, "tenders": []})

    result = run_candidate_enrichment(scope="focus", limit=10)
    attempts = ui_server.candidate_enrichment_attempts()

    assert result["ok"] is True
    assert calls == ["26PROC000000001", "AUTHORITY:AUTH-work"]
    assert result["summary"]["attempted"] == 2
    assert result["summary"]["enriched_with_eshidis"] == 1
    assert attempts["KIMDIS:26PROC000000001"]["linked_eshidis_ids"] == ["221473"]
    assert attempts["AUTHORITY:AUTH-work"]["source_signature"] == "sig-2"


def test_auto_document_fetch_stops_before_next_target_when_budget_expires(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    now = {"value": 0.0}
    calls = []
    monkeypatch.setattr(ui_server.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(
        ui_server,
        "candidate_enrichment_targets",
        lambda scope, limit: (
            [
                {
                    "row_key": "KIMDIS:26PROC000000001",
                    "identifier": "26PROC000000001",
                    "kind": "ΚΗΜΔΗΣ",
                    "source_signature": "sig-1",
                },
                {
                    "row_key": "AUTHORITY:AUTH-work",
                    "identifier": "AUTHORITY:AUTH-work",
                    "kind": "Φορέας",
                    "source_signature": "sig-2",
                },
            ],
            0,
        ),
    )

    def fake_selected_fetch(identifier):
        calls.append(identifier)
        now["value"] = 2.0
        return {"ok": True, "linked_eshidis_ids": []}

    monkeypatch.setattr(ui_server, "run_selected_fetch", fake_selected_fetch)
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}, "tenders": []})

    result = ui_server.run_auto_document_fetch(scope="focus", limit=10, max_seconds=1)

    assert result["ok"] is True
    assert calls == ["26PROC000000001"]
    assert result["summary"]["attempted"] == 1
    assert result["summary"]["remaining_targets"] == 1
    assert result["summary"]["stopped_by_time_budget"] is True


def test_ai_triage_job_runs_openai_backed_cli_and_refreshes_dashboard(monkeypatch) -> None:
    captured = {}

    def fake_run_cli_command(args):
        captured["args"] = args
        return {"ok": True, "returncode": 0, "stdout": '{"summary": {"errors": 0}}'}

    monkeypatch.setattr(ui_server, "run_cli_command", fake_run_cli_command)
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus", sort="deadline_asc": {"scope": scope, "sort": sort})
    monkeypatch.setattr(
        ui_server,
        "ai_triage_report_status",
        lambda: {"exists": True, "ok": True, "model": "gpt-4.1-mini", "summary": {"errors": 0}},
    )

    result = run_ai_triage(scope="focus", sort="deadline_asc", batch_size=20)

    assert result["ok"] is True
    assert captured["args"][:2] == ["sources", "ai-triage-report"]
    assert captured["args"][captured["args"].index("--scope") + 1] == "focus"
    assert captured["args"][captured["args"].index("--batch-size") + 1] == "20"
    assert result["ai_triage_report"]["model"] == "gpt-4.1-mini"


def test_discover_ui_starts_ai_triage_before_candidate_enrichment() -> None:
    assert "/api/ai-triage" in APP_JS
    assert "startAiTriageThenEnrichment" in APP_JS
    assert APP_JS.index("await pollJob(initial.job_id, 'AI διαλογή έργων με OpenAI')") < APP_JS.index("await startCandidateEnrichment()")


def test_selected_authority_fetch_extracts_linked_eshidis_and_chains_official_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Δήμος Πατρέων"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-work",
                        "title": "Διακήρυξη έργου Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/work",
                        "attachment_url": "https://e-patras.gr/work.pdf",
                        "attachment_urls": ["https://e-patras.gr/work.pdf"],
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_download(url, target_dir, index):
        path = target_dir / "work.pdf"
        path.write_bytes(b"pdf")
        return path, 3

    class FakeAnalysis:
        document_type = "tender_declaration"
        classification_confidence = 0.95
        matched_terms = ("διακήρυξη",)
        extraction_status = "TEXT_EXTRACTED"
        page_or_sheet_count = 1
        text_sample = "Άρθρο 2.2 URL resources/search/221473"
        full_text = "Άρθρο 2.2 πρόσβαση στο ΕΣΗΔΗΣ μέσω resources/search/221473"
        extraction_error = None

        def to_dict(self):
            return {
                "document_type": self.document_type,
                "classification_confidence": self.classification_confidence,
                "matched_terms": self.matched_terms,
                "extraction_status": self.extraction_status,
                "page_or_sheet_count": self.page_or_sheet_count,
                "text_sample": self.text_sample,
                "full_text": self.full_text,
                "extraction_error": self.extraction_error,
            }

    captured = {}

    def fake_run_cli_steps(steps, *, dashboard_scope=None):
        captured["steps"] = steps
        captured["dashboard_scope"] = dashboard_scope
        return {"ok": True, "steps": steps, "dashboard": {"scope": dashboard_scope}}

    monkeypatch.setattr(ui_server, "download_authority_document", fake_download)
    monkeypatch.setattr(ui_server, "analyze_document", lambda path, original_name=None: FakeAnalysis())
    monkeypatch.setattr(ui_server, "run_cli_steps", fake_run_cli_steps)

    result = run_selected_fetch("AUTHORITY:AUTH-work")
    preview = ui_server.authority_document_preview_payload("AUTHORITY:AUTH-work")

    assert result["ok"] is True
    assert result["linked_eshidis_ids"] == ["221473"]
    assert [step["name"] for step in captured["steps"]] == ["fetch_detail_221473", "download_files_221473"]
    assert preview["official_status"] == "LINKED_TO_ESHIDIS"
    assert preview["linked_eshidis_ids"] == ["221473"]
    assert preview["documents"][0]["text_sample"] == "Άρθρο 2.2 URL resources/search/221473"


def test_authority_fetch_reuses_unchanged_source_document(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Δήμος Πατρέων"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-work",
                        "title": "Διακήρυξη έργου Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/work",
                        "attachment_url": "https://e-patras.gr/work.pdf",
                        "attachment_urls": ["https://e-patras.gr/work.pdf"],
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_download(url, target_dir, index):
        calls.append(url)
        path = target_dir / "work.pdf"
        path.write_bytes(b"pdf")
        return path, 3

    class FakeAnalysis:
        def to_dict(self):
            return {
                "document_type": "tender_declaration",
                "classification_confidence": 0.95,
                "matched_terms": ["διακήρυξη"],
                "extraction_status": "TEXT_EXTRACTED",
                "page_or_sheet_count": 1,
                "text_sample": "Δεν περιέχει Α/Α ΕΣΗΔΗΣ",
                "full_text": "Δεν περιέχει Α/Α ΕΣΗΔΗΣ",
                "extraction_error": None,
            }

    monkeypatch.setattr(ui_server, "download_authority_document", fake_download)
    monkeypatch.setattr(ui_server, "analyze_document", lambda path, original_name=None: FakeAnalysis())
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}, "tenders": []})

    first = ui_server.run_authority_fetch("AUTHORITY:AUTH-work")
    second = ui_server.run_authority_fetch("AUTHORITY:AUTH-work")

    assert first["ok"] is True
    assert first["downloaded"] == 1
    assert first["skipped"] == 0
    assert second["ok"] is True
    assert second["downloaded"] == 0
    assert second["skipped"] == 1
    assert calls == ["https://e-patras.gr/work.pdf"]


def test_document_zip_includes_all_eshidis_latest_local_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    file_one = tmp_path / "work/download_audit/eshidis/221744/one.pdf"
    file_two = tmp_path / "work/download_audit/eshidis/221744/two.pdf"
    file_one.parent.mkdir(parents=True)
    file_one.write_bytes(b"one")
    file_two.write_bytes(b"two")
    db_path = tmp_path / "data/tender_radar.sqlite"
    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE tenders (id INTEGER PRIMARY KEY, eshidis_id TEXT);
            CREATE TABLE attachments (
              id INTEGER PRIMARY KEY,
              tender_id INTEGER,
              original_name TEXT,
              local_path TEXT,
              is_latest INTEGER
            );
            """
        )
        connection.execute("INSERT INTO tenders (id, eshidis_id) VALUES (1, '221744')")
        connection.execute(
            "INSERT INTO attachments (tender_id, original_name, local_path, is_latest) VALUES (1, 'one.pdf', ?, 1)",
            (str(file_one.relative_to(tmp_path)),),
        )
        connection.execute(
            "INSERT INTO attachments (tender_id, original_name, local_path, is_latest) VALUES (1, 'two.pdf', ?, 1)",
            (str(file_two.relative_to(tmp_path)),),
        )
        connection.commit()
    finally:
        connection.close()

    name, body = document_zip_bytes("221744")

    assert name == "tender_221744_documents.zip"
    assert body is not None
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert sorted(archive.namelist()) == ["one.pdf", "two.pdf"]
        assert archive.read("one.pdf") == b"one"


def test_authority_document_zip_includes_downloaded_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    document_dir = tmp_path / "work/download_audit/authority/AUTHORITY_AUTH-test"
    document_dir.mkdir(parents=True)
    document_path = document_dir / "municipal.pdf"
    document_path.write_bytes(b"municipal")
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "work/derived/authority_documents.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "row_key": "AUTHORITY:AUTH-1234567890abcdef",
                        "original_filename": "municipal.pdf",
                        "local_path": str(document_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    name, body = document_zip_bytes("AUTHORITY:AUTH-1234567890abcdef")

    assert name == "tender_AUTHORITY_AUTH-1234567890abcdef_documents.zip"
    assert body is not None
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.namelist() == ["municipal.pdf"]
        assert archive.read("municipal.pdf") == b"municipal"


def test_dismiss_tender_hides_row_from_dashboard(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    row_key = "AUTHORITY:AUTH-1234567890abcdef"
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-1234567890abcdef",
                        "title": "Έργο Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/tender",
                        "attachment_urls": ["https://e-patras.gr/a.pdf"],
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert dashboard_payload(scope="focus")["summary"]["visible"] == 1
    result = ui_server.dismiss_tender(row_key)
    payload = dashboard_payload(scope="focus")

    assert result["ok"] is True
    assert payload["summary"]["visible"] == 0
    assert payload["summary"]["ignored"] == 1


def test_dashboard_uses_cached_ai_triage_to_hide_drops(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-keep",
                        "title": "Έργο Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/tender",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    },
                        {
                            "source": "AUTHORITY",
                            "record_type": "AUTHORITY_WEB",
                            "official_id": "AUTH-drop",
                            "title": "Διακήρυξη έργου Πατρών προς απόρριψη",
                            "authority": "Δήμος Πατρέων",
                            "source_url": "https://e-patras.gr/el/admin",
                            "attachment_url": "https://e-patras.gr/admin.pdf",
                            "attachment_urls": ["https://e-patras.gr/admin.pdf"],
                            "matched_scopes": ["Δήμος Πατρέων"],
                            "match_notes": [],
                            "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "work/reports/ai_triage_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_key": "AUTHORITY:AUTH-keep",
                        "ai": {
                            "decision": "KEEP_ACTIVE_TENDER",
                            "confidence": 0.9,
                            "reason": "έργο",
                            "eshidis_id_candidates": [],
                            "keep_for_daily_review": True,
                        },
                    },
                    {
                        "row_key": "AUTHORITY:AUTH-drop",
                        "ai": {
                            "decision": "DROP_ADMIN",
                            "confidence": 0.9,
                            "reason": "διοικητικό",
                            "eshidis_id_candidates": [],
                            "keep_for_daily_review": False,
                        },
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus")

    assert payload["summary"]["visible"] == 1
    assert payload["summary"]["triage_hidden"] == 1
    assert payload["summary"]["triage_kept"] == 1
    assert payload["tenders"][0]["row_key"] == "AUTHORITY:AUTH-keep"
    assert payload["tenders"][0]["ai_triage"]["decision"] == "KEEP_ACTIVE_TENDER"

    unfiltered = dashboard_payload(scope="focus", apply_triage=False)
    assert unfiltered["summary"]["visible"] == 2
    assert unfiltered["summary"]["triage_hidden"] == 0


def test_admin_restore_ai_hidden_row_forces_keep(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-drop",
                "title": "Διακήρυξη έργου Πατρών προς επαναφορά",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/admin",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            }
        ],
    )
    (tmp_path / "work/reports/ai_triage_report.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_key": "AUTHORITY:AUTH-drop",
                        "ai": {
                            "decision": "DROP_ADMIN",
                            "confidence": 0.9,
                            "reason": "διοικητικό",
                            "eshidis_id_candidates": [],
                            "keep_for_daily_review": False,
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert dashboard_payload(scope="focus")["summary"]["visible"] == 0
    audit = ui_server.admin_audit_payload()
    assert audit["summary"]["ai_hidden"] == 1
    assert audit["hidden_rows"][0]["restorable"] is True

    restored = ui_server.restore_admin_row(row_key="AUTHORITY:AUTH-drop", reason="είναι ενεργό έργο")

    assert restored["ok"] is True
    payload = dashboard_payload(scope="focus")
    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["triage_override"]["action"] == "FORCE_KEEP"


def test_admin_restore_dismissed_row_removes_ignore(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-dismissed",
                "title": "Έργο Δήμου Πατρέων",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/tender",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            }
        ],
    )
    row_key = "AUTHORITY:AUTH-dismissed"

    ui_server.dismiss_tender(row_key)
    assert dashboard_payload(scope="focus")["summary"]["visible"] == 0
    assert ui_server.admin_audit_payload()["summary"]["dismissed"] == 1

    ui_server.restore_admin_row(row_key=row_key, reason="κατά λάθος")

    assert dashboard_payload(scope="focus")["summary"]["visible"] == 1
    assert ui_server.admin_audit_payload()["summary"]["dismissed"] == 0


def test_dashboard_hides_cached_authority_landing_pages(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities: []
regions:
  - id: aitoloakarnania
    name: "Περιφέρεια Δυτικής Ελλάδας / Π.Ε. Αιτωλοακαρνανίας"
    aliases: ["Αιτωλοακαρνανία"]
    nuts: ["EL631"]
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-d8c24f1b30d23177",
                        "title": "Έργα & Δράσεις",
                        "authority": "Περιφέρεια Δυτικής Ελλάδας / Π.Ε. Αιτωλοακαρνανίας",
                        "source_url": "https://pde.gov.gr/el/erga-drasis/",
                        "matched_scopes": ["Περιφέρεια Δυτικής Ελλάδας / Π.Ε. Αιτωλοακαρνανίας"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus", apply_triage=False)

    assert payload["summary"]["visible"] == 0


def test_authority_numeric_id_requires_eshidis_provenance() -> None:
    assert ui_server.authority_numeric_id_is_eshidis(
        "217922",
        {"record_type": "ESHIDIS", "title": "Περίληψη διακήρυξης"},
    )
    assert ui_server.authority_numeric_id_is_eshidis(
        "217922",
        {"record_type": "AUTHORITY_WEB", "row_text": "ΟΠΣ Ε.Σ.Η.ΔΗ.Σ Α/Α: 217922"},
    )
    assert not ui_server.authority_numeric_id_is_eshidis(
        "600334",
        {"record_type": "ESHIDIS", "source_url": "https://ted.europa.eu/el/notice/-/detail/449222-2026", "title": "κωδικός ΟΠΣ 600334"},
    )


def test_dashboard_filters_cached_non_public_works_authority_rows_without_gate_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Δήμος Πατρέων", "Πατρών"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-admin",
                        "title": "Πρόγραμμα εκλογών Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/admin",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    },
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-work",
                        "title": "Διακήρυξη έργου συντήρησης οδών Δήμου Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/work",
                        "attachment_url": "https://e-patras.gr/work.pdf",
                        "attachment_urls": ["https://e-patras.gr/work.pdf"],
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus", apply_triage=False)

    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["row_key"] == "AUTHORITY:AUTH-work"
    assert payload["tenders"][0]["public_works_gate"]["decision"] == "KEEP_PUBLIC_WORKS_CANDIDATE"


def test_dashboard_extracts_linked_eshidis_ids_from_authority_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        """
timezone: Europe/Athens
municipalities:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα", "Πατρών"]
    nuts: ["EL632"]
regions: []
""",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-abc",
                        "title": "Διακήρυξη έργου",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/tender",
                        "row_text": "Άρθρο 2.2 URL http://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/221744",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "match_notes": [],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = dashboard_payload(scope="focus", apply_triage=False)

    assert payload["tenders"][0]["linked_eshidis_ids"] == ["221744"]


def test_discovery_search_steps_run_eshidis_then_expanded_kimdis() -> None:
    steps = discovery_search_steps(limit=25, as_of_date="2026-07-17")

    assert [step["name"] for step in steps] == ["eshidis_discover", "expanded_report"]
    assert steps[0]["args"][:2] == ["sources", "discover-active"]
    assert steps[1]["args"][:2] == ["sources", "expanded-report"]
    assert "--eshidis-candidates" in steps[1]["args"]
    assert "work/reports/expanded_discovery_report.json" in steps[1]["args"]
    assert "2026-07-17" in steps[1]["args"]
    assert steps[1]["args"][steps[1]["args"].index("--kimdis-pages") + 1] == "20"


def test_backfill_discovery_retries_until_previous_window_overlap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        "timezone: Europe/Athens\nmunicipalities: []\nregions: []\n",
        encoding="utf-8",
    )
    append_discovery_run(
        tmp_path / "work/derived/discovery_runs.json",
        {
            "run_id": "previous",
            "success": True,
            "source_families": {"kimdis_proc": {"candidate_ids": ["26PROC000000001"]}},
        },
    )

    calls = []

    def fake_run_cli_process(args, *, timeout):
        calls.append(args)
        if args[:2] == ["sources", "discover-active"]:
            (tmp_path / "work/reports/eshidis_active_candidates.json").write_text(
                json.dumps({"candidates": [{"eshidis_id": "221800"}]}),
                encoding="utf-8",
            )
        if args[:2] == ["sources", "expanded-report"]:
            pages = int(args[args.index("--kimdis-pages") + 1])
            official_id = "26PROC000000001" if pages > 20 else "26PROC000000002"
            (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
                json.dumps(
                    {
                        "summary": {"errors": 0, "total_candidates": 1, "focus_candidates": 1},
                        "all_candidates": [{"source": "KIMDIS", "record_type": "PROC", "official_id": official_id}],
                        "focus_open_proc_candidates": [],
                        "focus_candidates": [],
                        "source_pages": [{"source": "khmdhs_notice", "record_type": "PROC", "page": 0, "items_returned": 50}],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "command": " ".join(args), "stdout": '{"summary": {"errors": 0}}', "stderr": ""}

    monkeypatch.setattr(ui_server, "run_cli_process", fake_run_cli_process)

    result = run_discovery_search(limit=100, backfill=True)

    assert result["ok"] is True
    assert len(result["discovery_runs"]) == 2
    assert result["discovery_run"]["watermark"]["complete"] is True
    expanded_calls = [args for args in calls if args[:2] == ["sources", "expanded-report"]]
    assert [args[args.index("--kimdis-pages") + 1] for args in expanded_calls] == ["20", "40"]


def test_discovery_skips_when_source_fingerprint_is_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text("timezone: Europe/Athens\nmunicipalities: []\nregions: []\n", encoding="utf-8")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": []}),
        encoding="utf-8",
    )
    fingerprint = {"ok": True, "hash": "same", "sources": [], "errors": []}
    ui_server.save_source_fingerprint(fingerprint)
    monkeypatch.setattr(ui_server, "quick_source_fingerprint", lambda timeout_seconds=8: fingerprint)

    def fail_run_cli_process(args, *, timeout):
        raise AssertionError("expensive discovery should be skipped")

    monkeypatch.setattr(ui_server, "run_cli_process", fail_run_cli_process)

    result = run_discovery_search(limit=100)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["skip_reason"] == "SKIPPED_UNCHANGED"
    assert result["source_preflight"]["status"] == "SKIPPED_UNCHANGED"


def test_discovery_runs_when_source_fingerprint_changed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text("timezone: Europe/Athens\nmunicipalities: []\nregions: []\n", encoding="utf-8")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": []}),
        encoding="utf-8",
    )
    ui_server.save_source_fingerprint({"ok": True, "hash": "old", "sources": [], "errors": []})
    monkeypatch.setattr(ui_server, "quick_source_fingerprint", lambda timeout_seconds=8: {"ok": True, "hash": "new", "sources": [], "errors": []})
    calls = []

    def fake_run_cli_process(args, *, timeout):
        calls.append(args)
        if args[:2] == ["sources", "discover-active"]:
            (tmp_path / "work/reports/eshidis_active_candidates.json").write_text(
                json.dumps({"candidates": []}),
                encoding="utf-8",
            )
        if args[:2] == ["sources", "expanded-report"]:
            (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
                json.dumps(
                    {
                        "summary": {"errors": 0, "total_candidates": 0, "focus_candidates": 0},
                        "all_candidates": [],
                        "focus_open_proc_candidates": [],
                        "focus_candidates": [],
                        "source_pages": [],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "command": " ".join(args), "stdout": '{"summary": {"errors": 0}}', "stderr": ""}

    monkeypatch.setattr(ui_server, "run_cli_process", fake_run_cli_process)

    result = run_discovery_search(limit=100)

    assert result.get("skipped") is not True
    assert [args[:2] for args in calls] == [["sources", "discover-active"], ["sources", "expanded-report"]]


def test_discovery_selectively_refreshes_eshidis_only_when_eshidis_source_changed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text("timezone: Europe/Athens\nmunicipalities: []\nregions: []\n", encoding="utf-8")
    (tmp_path / "config/sources.yml").write_text("authority_adapters: []\n", encoding="utf-8")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": []}),
        encoding="utf-8",
    )
    ui_server.save_source_fingerprint(
        {
            "ok": True,
            "hash": "old",
            "sources": [{"source_id": "eshidis_active_search", "adapter": "web_app", "token": "old"}],
            "errors": [],
        }
    )
    monkeypatch.setattr(
        ui_server,
        "quick_source_fingerprint",
        lambda timeout_seconds=8: {
            "ok": True,
            "hash": "new",
            "sources": [{"source_id": "eshidis_active_search", "adapter": "web_app", "token": "new"}],
            "errors": [],
        },
    )
    calls = []

    def fake_run_cli_process(args, *, timeout):
        calls.append(args)
        if args[:2] == ["sources", "discover-active"]:
            (tmp_path / "work/reports/eshidis_active_candidates.json").write_text(
                json.dumps({"candidates": []}),
                encoding="utf-8",
            )
        if args[:2] == ["sources", "expanded-report"]:
            assert args[args.index("--kimdis-source-id") + 1] == "__none__"
            assert args[args.index("--authority-source-id") + 1] == "__none__"
            assert args[args.index("--previous-report") + 1] == "work/reports/expanded_discovery_report.json"
            (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
                json.dumps(
                    {
                        "summary": {"errors": 0, "total_candidates": 0, "focus_candidates": 0},
                        "all_candidates": [],
                        "focus_open_proc_candidates": [],
                        "focus_candidates": [],
                        "source_pages": [],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "command": " ".join(args), "stdout": '{"summary": {"errors": 0}}', "stderr": ""}

    monkeypatch.setattr(ui_server, "run_cli_process", fake_run_cli_process)

    result = run_discovery_search(limit=100)

    assert result["ok"] is True
    assert [args[:2] for args in calls] == [["sources", "discover-active"], ["sources", "expanded-report"]]
    assert result["source_preflight"]["changed_source_ids"] == ["eshidis_active_search"]


def test_discovery_skips_when_successful_sources_are_unchanged_with_preflight_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text("timezone: Europe/Athens\nmunicipalities: []\nregions: []\n", encoding="utf-8")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": []}),
        encoding="utf-8",
    )
    previous = {
        "ok": True,
        "hash": "baseline",
        "sources": [
            {"source_id": "a", "adapter": "wordpress_category", "token": "1", "date": "2026-07-18"},
            {"source_id": "b", "adapter": "diavgeia_api", "token": "2", "date": "2026-07-18"},
            {"source_id": "c", "adapter": "html_listing", "token": "3"},
            {"source_id": "d", "adapter": "ted_api", "token": "4", "date": "2026-07-18"},
        ],
        "errors": [],
    }
    current = {
        "ok": False,
        "hash": "partial",
        "sources": [
            {"source_id": "a", "adapter": "wordpress_category", "token": "1", "date": "2026-07-18"},
            {"source_id": "c", "adapter": "html_listing", "token": "3"},
            {"source_id": "d", "adapter": "ted_api", "token": "4", "date": "2026-07-18"},
        ],
        "errors": [{"source": "b", "message": "HTTP Error 503"}],
    }
    ui_server.save_source_fingerprint(previous)
    monkeypatch.setattr(ui_server, "quick_source_fingerprint", lambda timeout_seconds=8: current)

    def fail_run_cli_process(args, *, timeout):
        raise AssertionError("temporary source failure should not force full discovery")

    monkeypatch.setattr(ui_server, "run_cli_process", fail_run_cli_process)

    result = run_discovery_search(limit=100)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["source_preflight"]["status"] == "SKIPPED_UNCHANGED_WITH_SOURCE_WARNINGS"
    assert result["source_preflight"]["errors"] == [{"source": "b", "message": "HTTP Error 503"}]


def test_discovery_selectively_refreshes_only_changed_non_eshidis_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text("timezone: Europe/Athens\nmunicipalities: []\nregions: []\n", encoding="utf-8")
    (tmp_path / "config/sources.yml").write_text(
        """
authority_adapters:
  - id: epatras_tenders
    adapter: drupal_listing
    url: https://e-patras.gr/el/tenders
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": [], "all_candidates": []}),
        encoding="utf-8",
    )
    ui_server.save_source_fingerprint(
        {
            "ok": True,
            "hash": "old",
            "sources": [{"source_id": "epatras_tenders", "adapter": "drupal_listing", "token": "old"}],
            "errors": [],
        }
    )
    monkeypatch.setattr(
        ui_server,
        "quick_source_fingerprint",
        lambda timeout_seconds=8: {
            "ok": True,
            "hash": "new",
            "sources": [{"source_id": "epatras_tenders", "adapter": "drupal_listing", "token": "new"}],
            "errors": [],
        },
    )
    calls = []

    def fake_run_cli_process(args, *, timeout):
        calls.append(args)
        assert args[:2] != ["sources", "discover-active"]
        if args[:2] == ["sources", "expanded-report"]:
            assert args[args.index("--authority-source-id") + 1] == "epatras_tenders"
            assert args[args.index("--kimdis-source-id") + 1] == "__none__"
            assert args[args.index("--previous-report") + 1] == "work/reports/expanded_discovery_report.json"
            (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
                json.dumps(
                    {
                        "summary": {"errors": 0, "total_candidates": 0, "focus_candidates": 0},
                        "all_candidates": [],
                        "focus_open_proc_candidates": [],
                        "focus_candidates": [],
                        "source_pages": [{"source": "epatras_tenders", "status": "FETCHED_CHANGED"}],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "command": " ".join(args), "stdout": '{"summary": {"errors": 0}}', "stderr": ""}

    monkeypatch.setattr(ui_server, "run_cli_process", fake_run_cli_process)

    result = run_discovery_search(limit=100)

    assert result["ok"] is True
    assert [args[:2] for args in calls] == [["sources", "expanded-report"]]


def test_discovery_selectively_refreshes_changed_kimdis_family(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text("timezone: Europe/Athens\nmunicipalities: []\nregions: []\n", encoding="utf-8")
    (tmp_path / "config/sources.yml").write_text("authority_adapters: []\n", encoding="utf-8")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": [], "all_candidates": []}),
        encoding="utf-8",
    )
    ui_server.save_source_fingerprint(
        {
            "ok": True,
            "hash": "old",
            "sources": [{"source_id": "khmdhs_auction", "adapter": "api_post", "token": "old"}],
            "errors": [],
        }
    )
    monkeypatch.setattr(
        ui_server,
        "quick_source_fingerprint",
        lambda timeout_seconds=8: {
            "ok": True,
            "hash": "new",
            "sources": [{"source_id": "khmdhs_auction", "adapter": "api_post", "token": "new"}],
            "errors": [],
        },
    )
    calls = []

    def fake_run_cli_process(args, *, timeout):
        calls.append(args)
        assert args[:2] != ["sources", "discover-active"]
        if args[:2] == ["sources", "expanded-report"]:
            assert args[args.index("--kimdis-source-id") + 1] == "khmdhs_auction"
            assert args[args.index("--authority-source-id") + 1] == "__none__"
            assert args[args.index("--previous-report") + 1] == "work/reports/expanded_discovery_report.json"
            (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
                json.dumps(
                    {
                        "summary": {"errors": 0, "total_candidates": 0, "focus_candidates": 0},
                        "all_candidates": [],
                        "focus_open_proc_candidates": [],
                        "focus_candidates": [],
                        "source_pages": [{"source": "khmdhs_auction", "status": "FETCHED_CHANGED"}],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "command": " ".join(args), "stdout": '{"summary": {"errors": 0}}', "stderr": ""}

    monkeypatch.setattr(ui_server, "run_cli_process", fake_run_cli_process)

    result = run_discovery_search(limit=100)

    assert result["ok"] is True
    assert [args[:2] for args in calls] == [["sources", "expanded-report"]]


def test_interest_reason_uses_locations_config() -> None:
    assert interest_reason("Έργο στον Δήμο Πατρέων EL632") == "Δήμος Πατρέων"


def test_region_focus_uses_included_units_not_broad_nuts_prefix() -> None:
    assert interest_reason("Έργο στην Περιφερειακή Ενότητα Φωκίδας EL645") == "Περιφέρεια Στερεάς Ελλάδας - Φωκίδα"
    assert interest_reason("Έργο στη Φθιώτιδα EL644") is None


def test_ambiguous_glyfada_is_kept_for_dorida_review() -> None:
    assert interest_reason("Δημοτική οδοποιία ΔΕ Γλυφάδας") == "Δήμος Δωρίδος (ασαφές τοπωνύμιο: Γλυφάδα)"
    assert interest_reason("Δημοτική οδοποιία ΔΕ Γλυφάδας Δήμος Δωρίδος") == "Δήμος Δωρίδος"
    assert interest_reason("Ανάπλαση Δήμος Γλυφάδας Αττική EL30") is None


def test_interest_reason_matches_amfilochia_alias_variants() -> None:
    assert interest_reason("ΕΡΓΟ ΣΤΟ ΘΕΡΙΑΚΗΣΙ") == "Δήμος Αμφιλοχίας"
    assert interest_reason("εργο στο Θεριακήσιο") == "Δήμος Αμφιλοχίας"
    assert interest_reason("εργο στο Θεργιακησι") == "Δήμος Αμφιλοχίας"


def test_short_alias_does_not_match_inside_larger_word() -> None:
    assert not focus_term_matches("κατασκευη κτηριου", "Ρίο")
    assert focus_term_matches("εργο στο ριο", "Ρίο")


def test_preview_kind_finds_basic_documents_from_type_or_name() -> None:
    assert preview_kind("tender_declaration", "file.pdf") == "declaration"
    assert preview_kind("", "ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ.pdf") == "technical_description"
    assert preview_kind("", "ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf") == "budget"


def test_short_text_sample_limits_preview_payload() -> None:
    sample = short_text_sample("λέξη " * 200, limit=40)

    assert sample is not None
    assert len(sample) <= 43
    assert sample.endswith("...")
