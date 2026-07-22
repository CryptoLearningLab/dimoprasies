from pathlib import Path
from datetime import date, datetime, timezone
import json
import sqlite3
from types import SimpleNamespace
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
        json.dumps(
            {
                "focus_authority_candidates": [
                    {"submission_deadline": "2026-08-20T10:00:00", **row}
                    for row in rows
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_ui_shows_current_version_badge() -> None:
    assert "versionBadge" in INDEX_HTML
    assert f"v{ui_server.__version__}" in INDEX_HTML


def test_ui_exposes_source_polling_audit() -> None:
    assert 'id="sourceAuditSummary"' in INDEX_HTML
    assert 'id="sourceAuditRows"' in INDEX_HTML
    assert "<th>Health</th>" in INDEX_HTML
    assert "/api/source-polling" in APP_JS
    assert "renderSourcePolling" in APP_JS
    assert "sourceHealthClass" in APP_JS
    assert "Health warnings" in APP_JS
    assert "refreshRuntimeViews" in APP_JS
    assert "$('entalmata').classList.contains('active')" in APP_JS
    assert "$('workflow').classList.contains('active')" in APP_JS


def test_ui_preview_renders_operational_explanation() -> None:
    assert "renderTenderExplanation" in APP_JS
    assert "why_visible" in APP_JS
    assert "project_sources" in APP_JS
    assert "project_operations" in APP_JS
    assert "project_timeline" in APP_JS
    assert "profile_fit" in APP_JS
    assert "ai_confidence_band" in APP_JS
    assert "AI band" in APP_JS
    assert "Γιατί εμφανίζεται" in APP_JS


def test_ui_exposes_user_interest_profile_controls() -> None:
    assert 'id="profileIncludeInput"' in INDEX_HTML
    assert 'id="profileExcludeInput"' in INDEX_HTML
    assert 'id="profileCategoryOptions"' in INDEX_HTML
    assert "Κατηγορίες έργων που με ενδιαφέρουν" in INDEX_HTML
    assert 'id="profileMinBudgetInput"' in INDEX_HTML
    assert 'id="profileMaxBudgetInput"' in INDEX_HTML
    assert "/api/user/interest-profile" in APP_JS
    assert "saveInterestProfile" in APP_JS
    assert "loadInterestProfile" in APP_JS
    assert "selectedProfileCategoryIds" in APP_JS
    assert ".profileCategoryOption:has(input:checked)" in STYLES_CSS
    assert ".profileCategoryOption input" in STYLES_CSS
    assert "grid-template-columns: 12px minmax(0, 1fr)" in STYLES_CSS
    assert "max-width: 1720px" in STYLES_CSS


def test_ui_preview_renders_project_identity_and_source_merge() -> None:
    assert "project_identity" in APP_JS
    assert "source_merge" in APP_JS
    assert "Ταυτότητα έργου" in APP_JS
    assert "Dedup" in APP_JS


def test_ui_preview_renders_greek_category_audit() -> None:
    assert "category_audit" in APP_JS
    assert "Κατηγοριοποίηση" in APP_JS
    assert "confidence" in APP_JS


def test_category_audit_matches_road_works_with_cpv_and_greek_terms() -> None:
    audit = ui_server.category_audit_for_row(
        {
            "title": "ΔΗΜΟΤΙΚΗ ΟΔΟΠΟΙΙΑ Δ.Ε ΕΥΠΑΛΙΟΥ",
            "cpv_code": "45233141-9",
            "text_sample": (
                "CPV : 45233141-9 Εργασίες συντήρησης οδών με ασφαλτόστρωση, "
                "τσιμεντόστρωση και βελτίωση βατότητας."
            ),
        }
    )

    assert audit["primary"]["id"] == "road_works"
    assert audit["primary"]["label"] == "Οδοποιία / οδικά έργα"
    assert audit["primary"]["confidence"] >= 0.85
    assert audit["needs_review"] is False
    assert any(evidence["kind"] == "CPV" for evidence in audit["primary"]["evidence"])


def test_category_audit_flags_supply_service_as_negative_without_auto_drop() -> None:
    audit = ui_server.category_audit_for_row({"title": "Προμήθεια Καυσίμων & Λιπαντικών για δύο έτη"})

    assert audit["negative_labels"][0]["id"] == "supply_service_out"
    assert audit["needs_review"] is True
    assert audit["band"] == "NEEDS_REVIEW"


def test_ui_exposes_client_side_deadline_watch() -> None:
    assert 'id="deadlineWatchBuckets"' in INDEX_HTML
    assert 'id="deadlineWatchSummary"' in INDEX_HTML
    assert "Λήγουν σύντομα" in INDEX_HTML
    assert "deadlineWatchBuckets" in APP_JS
    assert "renderDeadlineWatch(payload.tenders || [])" in APP_JS
    assert "/api/deadline" not in APP_JS
    assert "/api/expiring" not in APP_JS


def test_cached_payload_reuses_builder_and_marks_cache_hit() -> None:
    ui_server.invalidate_ui_payload_cache()
    calls = {"count": 0}

    def builder():
        calls["count"] += 1
        return {"ok": True, "value": calls["count"]}

    first = ui_server.cached_payload(("unit",), builder, ttl_seconds=30)
    second = ui_server.cached_payload(("unit",), builder, ttl_seconds=30)

    assert calls["count"] == 1
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert second["value"] == 1
    ui_server.invalidate_ui_payload_cache()


def test_cached_dashboard_payload_does_not_run_expired_cleanup(monkeypatch) -> None:
    ui_server.invalidate_ui_payload_cache()
    captured = {}

    def fake_dashboard_payload(*, scope, sort, user_email=None, perform_expired_cleanup=True, **kwargs):
        captured["perform_expired_cleanup"] = perform_expired_cleanup
        return {"ok": True, "scope": scope, "sort": sort, "user_email": user_email}

    monkeypatch.setattr(ui_server, "dashboard_payload", fake_dashboard_payload)

    payload = ui_server.cached_dashboard_payload(scope="focus", sort="deadline_asc", user_email="owner@example.test")

    assert payload["ok"] is True
    assert captured["perform_expired_cleanup"] is False
    ui_server.invalidate_ui_payload_cache()


def test_ui_exposes_entalmata_tab() -> None:
    assert 'data-view="entalmata"' in INDEX_HTML
    assert "Εντάλματα τελευταίων 15 ημερών" in INDEX_HTML
    assert 'id="entalmataRows"' in INDEX_HTML
    assert 'id="entalmataArchivedCount"' in INDEX_HTML
    assert "Δημόσια<br>έργα" in INDEX_HTML
    assert "Αντίστροφη<br>αναζήτηση" in INDEX_HTML
    assert "/api/entalmata" in APP_JS
    assert "/api/entalmata/scan" in APP_JS
    assert "/api/entalmata-file" in INDEX_HTML + APP_JS
    assert "Τίτλος έργου" in APP_JS
    assert "renderEntalmata" in APP_JS


def test_ui_exposes_reverse_search_tab() -> None:
    assert 'data-view="workflow"' in INDEX_HTML
    assert "Αντίστροφη<br>αναζήτηση" in INDEX_HTML
    assert 'id="reverseSearchInput"' in INDEX_HTML
    assert 'id="reverseSearchBtn"' in INDEX_HTML
    assert 'id="reverseSearchResults"' in INDEX_HTML
    assert "/api/reverse-search" in APP_JS
    assert "runReverseSearch" in APP_JS
    assert "renderReverseSearch" in APP_JS


def test_login_screen_exposes_password_reset_and_legal_footer() -> None:
    assert 'id="forgotPasswordBtn"' in INDEX_HTML
    assert "/api/auth/request-password-reset" in APP_JS
    assert "Όροι χρήσης" in INDEX_HTML
    assert "Privacy" in INDEX_HTML
    assert "Οδηγίες" in INDEX_HTML


def test_admin_panel_exposes_production_secrets_form() -> None:
    assert 'id="teeUsernameInput"' in INDEX_HTML
    assert 'id="teePasswordInput"' in INDEX_HTML
    assert 'id="saveTeeSecretsBtn"' in INDEX_HTML
    assert "/api/admin/secrets" in APP_JS
    assert "renderAdminSecrets" in APP_JS


def test_admin_secret_payload_redacts_values_and_writes_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / ".env.local").write_text(
        'SMTP_HOST="smtp.example.test"\nTEE_USERNAME="old-user"\n',
        encoding="utf-8",
    )

    result = ui_server.update_admin_secrets(
        {"TEE_USERNAME": "tee-user", "TEE_PASSWORD": "tee-pass"},
        actor_email="owner@example.test",
    )
    text = (tmp_path / ".env.local").read_text(encoding="utf-8")

    assert 'SMTP_HOST="smtp.example.test"' in text
    assert 'TEE_USERNAME="tee-user"' in text
    assert 'TEE_PASSWORD="tee-pass"' in text
    assert result["keys"]["TEE_USERNAME"] == {"configured": True}
    assert result["keys"]["TEE_PASSWORD"] == {"configured": True}
    assert "tee-pass" not in json.dumps(result)
    assert result["actor_email"] == "owner@example.test"


def test_reverse_search_payload_searches_active_dashboard_and_documents(monkeypatch, tmp_path: Path) -> None:
    text_path = tmp_path / "declaration.txt"
    text_path.write_text("Τεχνική περιγραφή για γέφυρα και ασφαλτόστρωση δημοτικής οδού.", encoding="utf-8")

    def fake_dashboard_payload(*args, **kwargs):
        return {
            "tenders": [
                {
                    "row_key": "221001",
                    "display_id": "221001",
                    "eshidis_id": "221001",
                    "source_label": "ΕΣΗΔΗΣ",
                    "title": "Συντήρηση υποδομών",
                    "authority_name": "ΔΗΜΟΣ ΔΟΚΙΜΗΣ",
                    "region": "EL631",
                    "budget_display": "10.000,00 EUR",
                    "deadline_display": "30-07-2026 10:00:00",
                    "official_url": "https://example.test/221001",
                    "interest_reason": "Δήμος Δοκιμής",
                }
            ]
        }

    monkeypatch.setattr(ui_server, "dashboard_payload", fake_dashboard_payload)
    monkeypatch.setattr(
        ui_server,
        "list_searchable_documents",
        lambda db_path: [
            SimpleNamespace(
                eshidis_id="221001",
                document_id=7,
                document_type="technical_description",
                original_name="technical.pdf",
                local_path=None,
                text_path=str(text_path),
                text_sample=None,
            )
        ],
    )

    payload = ui_server.reverse_search_payload({"query": "ασφαλτοστρωση"})

    assert payload["ok"] is True
    assert payload["summary"]["active_rows_searched"] == 1
    assert payload["summary"]["matches"] == 1
    assert payload["results"][0]["display_id"] == "221001"
    assert payload["results"][0]["matches"][0]["label"] == "technical.pdf"


def test_nationwide_scope_is_disabled_in_ui_and_api() -> None:
    assert "allGreeceToggle" not in INDEX_HTML
    assert "allGreeceToggle" not in APP_JS
    assert "Λήψη έργων από όλη την Ελλάδα" not in INDEX_HTML
    assert ui_server.dashboard_scope("all") == "focus"


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
    assert 'id="adminReviewRows"' in INDEX_HTML
    assert 'id="adminReviewQueueCount"' in INDEX_HTML
    assert "False negative review queue" in INDEX_HTML
    assert "renderAdminReviewQueue" in APP_JS
    assert 'id="passwordSetupBox"' in INDEX_HTML
    assert 'id="inviteUserBtn"' in INDEX_HTML
    assert "/api/auth/login" in APP_JS
    assert "/api/auth/status" in APP_JS
    assert "/api/auth/logout" in APP_JS
    assert "/api/admin/set-password" in APP_JS
    assert "/api/admin/invite-user" in APP_JS
    assert "/api/admin/update-user-role" in APP_JS
    assert "/api/admin/users" in APP_JS
    assert "/api/admin/audit" in APP_JS
    assert "/api/admin/restore" in APP_JS
    assert "/api/admin/review-feedback" in APP_JS
    assert "Σωστά κόπηκε" in APP_JS
    assert "Λάθος, κράτα τέτοια" in APP_JS


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
    monkeypatch.setattr(ui_server, "email_alert_recipients", lambda recipient=None: ["owner@example.test"])
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


def test_password_reset_sends_setup_link_for_existing_user(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    sent: list[dict[str, str]] = []

    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(
        ui_server,
        "send_email_alert",
        lambda recipient, subject, text_body, html_body: sent.append(
            {"recipient": recipient, "subject": subject, "text": text_body, "html": html_body}
        ),
    )
    monkeypatch.setattr(ui_server.secrets, "token_urlsafe", lambda size=32: "reset-token")
    ui_server.upsert_admin_user(db_path, email="owner@example.test", role="admin", enabled=True)

    result = ui_server.request_password_reset({"email": "owner@example.test"}, base_url="https://example.test")

    assert result["ok"] is True
    assert result["sent"] is True
    assert sent[0]["recipient"] == "owner@example.test"
    assert "https://example.test/password-setup?token=reset-token" in sent[0]["text"]
    assert "60 λεπτά" in sent[0]["text"]


def test_password_setup_invite_expires_after_configured_minutes(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"

    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(ui_server.secrets, "token_urlsafe", lambda size=32: "ttl-token")

    ui_server.create_password_setup_invite(
        email="owner@example.test",
        role="admin",
        created_by="test",
        base_url="https://example.test",
    )

    invite = ui_server.get_admin_invite(db_path, ui_server.hash_reset_token("ttl-token"))
    assert invite is not None
    created_at = datetime.fromisoformat(invite.created_at)
    expires_at = datetime.fromisoformat(invite.expires_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    delta_seconds = (expires_at - created_at).total_seconds()
    assert ui_server.PASSWORD_SETUP_TOKEN_TTL_MINUTES * 60 - 5 <= delta_seconds <= ui_server.PASSWORD_SETUP_TOKEN_TTL_MINUTES * 60


def test_password_reset_does_not_reveal_missing_user(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    sent: list[str] = []

    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(ui_server, "send_email_alert", lambda recipient, subject, text_body, html_body: sent.append(text_body))

    result = ui_server.request_password_reset({"email": "missing@example.test"}, base_url="https://example.test")

    assert result == {"ok": True, "sent": True}
    assert sent == []


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
    assert user.id >= 1
    assert user.role == "user"
    assert ui_server.verify_admin_user_password(email="worker@example.test", password="long-secure-password") is False


def test_admin_invite_accepts_tester_role(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(ui_server, "send_email_alert", lambda recipient, subject, text_body, html_body: None)
    monkeypatch.setattr(ui_server.secrets, "token_urlsafe", lambda size=32: "tester-token")

    result = ui_server.invite_admin_user(
        {"email": "tester@example.test", "role": "tester"},
        inviter="owner@example.test",
        base_url="https://example.test",
    )
    user = ui_server.get_admin_user(db_path, "tester@example.test")

    assert result["role"] == "tester"
    assert user is not None
    assert user.role == "tester"


def test_admin_invite_accepts_pricing_role(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    monkeypatch.setattr(ui_server, "send_email_alert", lambda recipient, subject, text_body, html_body: None)
    monkeypatch.setattr(ui_server.secrets, "token_urlsafe", lambda size=32: "pricing-token")

    result = ui_server.invite_admin_user(
        {"email": "pricing@example.test", "role": "pricing"},
        inviter="owner@example.test",
        base_url="https://example.test",
    )
    user = ui_server.get_admin_user(db_path, "pricing@example.test")

    assert result["role"] == "pricing"
    assert user is not None
    assert user.role == "pricing"


def test_update_admin_user_role_accepts_email_or_id_and_protects_last_admin(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)
    owner = ui_server.upsert_admin_user(db_path, email="owner@example.test", role="admin", enabled=True)
    worker = ui_server.upsert_admin_user(db_path, email="worker@example.test", role="user", enabled=True)

    by_email = ui_server.update_admin_user_role(
        {"identifier": "worker@example.test", "role": "tester"},
        actor_email="owner@example.test",
    )
    by_id = ui_server.update_admin_user_role(
        {"identifier": f"#{worker.id}", "role": "user"},
        actor_email="owner@example.test",
    )

    assert by_email["user"]["role"] == "tester"
    assert by_id["user"]["role"] == "user"
    try:
        ui_server.update_admin_user_role({"identifier": str(owner.id), "role": "user"}, actor_email="other-admin@example.test")
    except ValueError as exc:
        assert "last enabled admin" in str(exc)
    else:
        raise AssertionError("Expected last-admin protection.")


def test_admin_users_payload_exposes_user_id(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(ui_server, "runtime_db_path", lambda: db_path)

    ui_server.upsert_admin_user(db_path, email="owner@example.test", role="admin", enabled=True)
    payload = ui_server.admin_users_payload()

    assert payload["users"][0]["id"] >= 1
    assert payload["users"][0]["email"] == "owner@example.test"


def test_admin_users_ui_has_id_and_mobile_labels() -> None:
    assert "<th>ID</th>" in INDEX_HTML
    assert "adminUsersTableWrap" in INDEX_HTML
    assert 'id="roleUserIdentifierInput"' in INDEX_HTML
    assert 'id="updateUserRoleBtn"' in INDEX_HTML
    assert 'id="pricingNavBtn"' in INDEX_HTML
    assert 'value="pricing"' in INDEX_HTML
    assert 'data-label="ID"' in APP_JS
    assert "userIdBadge" in APP_JS
    assert ".adminUsersTable" in STYLES_CSS


def test_front_page_hides_source_audit_but_keeps_backend_audit() -> None:
    assert '<details class="sourceAudit" open hidden>' in INDEX_HTML
    assert 'id="sourceAuditRows"' in INDEX_HTML
    assert "/api/source-polling" in APP_JS


def test_dashboard_pills_use_wrapping_stack() -> None:
    assert "function pillStack" in APP_JS
    assert "pillStack" in APP_JS
    assert ".pillStack" in STYLES_CSS
    assert "overflow-wrap: anywhere" in STYLES_CSS


def test_mobile_table_label_column_fits_long_budget_label() -> None:
    assert "Προϋπολογισμός" in APP_JS
    assert "grid-template-columns: minmax(146px, 38%) minmax(0, 1fr)" in STYLES_CSS


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
    for index in range(3):
        ui_server.record_source_run(
            ui_server.runtime_db_path(),
            run_id=f"run-{index}",
            source_id="nafpaktos_tenders",
            started_at=f"2026-07-18T10:0{index}:00+00:00",
            finished_at=f"2026-07-18T10:0{index}:01+00:00",
            status="ERROR",
            error="timeout",
        )

    payload = source_polling_payload()

    assert payload["summary"]["configured_total"] == 3
    assert payload["summary"]["tracked_total"] == 2
    assert payload["summary"]["changed_total"] == 1
    assert payload["summary"]["selective_changed_total"] == 1
    assert payload["summary"]["error_total"] == 1
    assert payload["summary"]["selective_error_total"] == 1
    assert payload["summary"]["health_warning_total"] == 1
    assert payload["summary"]["never_checked_total"] == 1
    by_id = {row["source_id"]: row for row in payload["rows"]}
    assert by_id["eshidis_active_search"]["selective_refresh_capable"] is True
    assert by_id["nafpaktos_tenders"]["last_error"] == "timeout"
    assert by_id["nafpaktos_tenders"]["health"]["status"] == "DEGRADED"
    assert by_id["nafpaktos_tenders"]["health"]["consecutive_failures"] == 3
    assert by_id["template_source"]["last_status"] == "NEVER_CHECKED"


def test_source_health_marks_disable_candidate_after_repeated_failures() -> None:
    rows = [
        {"status": "ERROR", "error": "HTTP Error 503", "started_at": f"2026-07-18T10:0{index}:00+00:00"}
        for index in range(5)
    ]

    health = ui_server.source_health_from_runs(rows)

    assert health["status"] == "DISABLE_CANDIDATE"
    assert health["recent_failures"] == 5
    assert health["consecutive_failures"] == 5


def test_email_alerts_payload_skips_rows_already_sent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(ui_server, "email_alert_recipients", lambda recipient=None: ["owner@example.test"])
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


def test_email_alerts_payload_supports_multiple_recipients(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(ui_server, "email_alert_recipients", lambda recipient=None: ["one@example.test", "two@example.test"])
    monkeypatch.setattr(
        ui_server,
        "dashboard_payload",
        lambda scope="focus", sort="deadline_asc": {
            "summary": {"visible": 1},
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
                }
            ],
        },
    )
    ui_server.record_notification_sent(
        ui_server.runtime_db_path(),
        row_key="ESHIDIS:221744",
        channel="email",
        recipient="one@example.test",
        subject="old",
    )

    payload = email_alerts_payload(dry_run=True)

    assert payload["recipients"] == ["one@example.test", "two@example.test"]
    assert payload["new_count"] == 1
    assert payload["skipped_already_sent"] == 1
    by_recipient = {item["recipient"]: item for item in payload["per_recipient"]}
    assert by_recipient["one@example.test"]["new_count"] == 0
    assert by_recipient["one@example.test"]["skipped_already_sent"] == 1
    assert by_recipient["two@example.test"]["new_count"] == 1
    assert by_recipient["two@example.test"]["skipped_already_sent"] == 0


def test_email_digest_groups_operational_signals(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(ui_server, "email_alert_recipients", lambda recipient=None: ["owner@example.test"])
    monkeypatch.setattr(
        ui_server,
        "dashboard_payload",
        lambda scope="focus", sort="deadline_asc": {
            "summary": {"visible": 1},
            "tenders": [
                {
                    "row_key": "KIMDIS:26PROC000000001",
                    "display_id": "26PROC000000001",
                    "source_label": "ΚΗΜΔΗΣ",
                    "official_url": "https://example.test/notice",
                    "title": "Αναπλάσεις πλατείας",
                    "authority_name": "Δήμος Ναυπακτίας",
                    "budget_display": "750.000",
                    "budget_sort": 750000,
                    "deadline_display": "2026-07-24 10:00",
                    "deadline_sort": "2026-07-24 10:00",
                    "why_visible": [
                        {"label": "Περιοχή", "text": "Ταιριάζει με Ναυπακτία."},
                        {"label": "Προθεσμία", "text": "Ενεργή προθεσμία: 2026-07-24 10:00."},
                    ],
                    "project_operations": [
                        {"label": "Έγγραφα", "status": "pending", "text": "Δεν έχουν καταγραφεί ακόμα τοπικά έγγραφα."},
                        {"label": "Email", "status": "pending", "text": "Δεν έχει καταγραφεί αποστολή email για αυτό το έργο."},
                    ],
                }
            ],
        },
    )

    payload = email_alerts_payload(dry_run=True)

    assert "Σήματα προσοχής" in payload["text_body"]
    assert "Χωρίς έγγραφα" in payload["text_body"]
    assert "Χωρίς ΕΣΗΔΗΣ" in payload["text_body"]
    assert "Γιατί σε ενδιαφέρει: Ταιριάζει με Ναυπακτία." in payload["text_body"]
    assert "Σήματα: λήγει σύντομα, χωρίς έγγραφα, χωρίς ΕΣΗΔΗΣ" in payload["text_body"]
    assert "<h2>Σήματα προσοχής</h2>" in payload["html_body"]


def test_email_alerts_payload_includes_clickable_entalmata_once_per_recipient(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(ui_server, "email_alert_recipients", lambda recipient=None: ["one@example.test", "two@example.test"])
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus", sort="deadline_asc": {"summary": {}, "tenders": []})
    monkeypatch.setattr(
        ui_server,
        "entalmata_email_rows",
        lambda: [
            {
                "row_key": "ENTALMA:6ΤΩΚΚ2Π-Ω2Β",
                "ada": "6ΤΩΚΚ2Π-Ω2Β",
                "title": "ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ 1739-2026-07-09",
                "subject": "Εκκαθάριση-εντολή πληρωμής",
                "org_name": "Περιφέρεια Στερεάς Ελλάδας",
                "issue_date": "2026-07-09",
                "protocol_number": "1739",
                "document_url": "https://diavgeia.gov.gr/doc/6ΤΩΚΚ2Π-Ω2Β",
                "project_title": "Αποκατάσταση βλαβών",
                "matched_keywords": ["ΛΑΠΤΩ"],
            }
        ],
    )
    ui_server.record_notification_sent(
        ui_server.runtime_db_path(),
        row_key="ENTALMA:6ΤΩΚΚ2Π-Ω2Β",
        channel="entalmata_email",
        recipient="one@example.test",
        subject="old",
    )

    payload = email_alerts_payload(dry_run=True)

    assert payload["candidate_rows"] == 0
    assert payload["entalmata_candidate_rows"] == 1
    assert payload["new_count"] == 0
    assert payload["new_entalmata_count"] == 1
    assert payload["entalmata_skipped_already_sent"] == 1
    by_recipient = {item["recipient"]: item for item in payload["per_recipient"]}
    assert by_recipient["one@example.test"]["new_entalmata_count"] == 0
    assert by_recipient["two@example.test"]["new_entalmata_count"] == 1
    assert "https://diavgeia.gov.gr/doc/6ΤΩΚΚ2Π-Ω2Β" in by_recipient["two@example.test"]["html_body"]


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
    monkeypatch.setattr(
        ui_server,
        "run_scheduled_entalmata_scan",
        lambda: {"ok": True, "skipped": False, "summary": {"matched": 2, "archived": 1}},
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
    assert payload["entalmata"]["summary"] == {"matched": 2, "archived": 1}
    assert payload["coverage_metrics"]["sources_checked"] == 2
    assert payload["coverage_metrics"]["public_works_new_email_rows"] == 1
    assert payload["monitoring_status"] == "OK"
    assert payload["monitoring_alerts"] == []
    assert payload["monitoring_email"]["skipped"] is True
    assert report.exists()
    assert markdown.exists()
    markdown_text = markdown.read_text(encoding="utf-8")
    assert "Scheduled Poll and Alert" in markdown_text
    assert "## Coverage" in markdown_text
    assert "## Monitoring Alerts" in markdown_text
    assert "## Entalmata" in markdown_text


def test_scheduled_poll_reports_source_monitoring_alerts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(
        ui_server,
        "run_discovery_search",
        lambda limit, backfill=False: {
            "ok": True,
            "skipped": False,
            "source_preflight": {"changed_source_ids": ["diavgeia"]},
            "steps": [],
            "dashboard": {"summary": {"visible": 0}},
        },
    )
    monkeypatch.setattr(
        ui_server,
        "run_incremental_ai_triage",
        lambda scope="focus", sort="deadline_asc", batch_size=20: {"ok": True, "summary": {"rows": 0}},
    )
    monkeypatch.setattr(
        ui_server,
        "run_auto_document_fetch",
        lambda scope="focus", limit=50: {"ok": True, "summary": {"attempted": 0}},
    )
    monkeypatch.setattr(
        ui_server,
        "run_email_alerts",
        lambda scope="focus", sort="deadline_asc", recipient=None, dry_run=False: {
            "ok": True,
            "dry_run": dry_run,
            "recipient": recipient,
            "recipients": ["owner@example.test"],
            "candidate_rows": 0,
            "new_count": 0,
            "skipped_already_sent": 0,
            "sent": 0,
            "sent_emails": 0,
        },
    )
    monkeypatch.setattr(
        ui_server,
        "source_polling_payload",
        lambda: {
            "summary": {
                "configured_total": 2,
                "changed_total": 1,
                "unchanged_total": 0,
                "error_total": 1,
                "health_warning_total": 1,
            },
            "rows": [
                {"source_id": "diavgeia", "last_status": "ERROR", "last_error": "HTTP 503"},
                {"source_id": "eshidis_active_search", "last_status": "CHANGED"},
            ],
        },
    )
    monkeypatch.setattr(ui_server, "run_scheduled_entalmata_scan", lambda: {"ok": True, "summary": {}})

    payload = run_scheduled_poll_and_alert(recipient="owner@example.test", dry_run=True)

    assert payload["ok"] is True
    assert payload["monitoring_status"] == "WARNING"
    codes = {alert["code"] for alert in payload["monitoring_alerts"]}
    assert {"SOURCE_ERRORS", "SOURCE_HEALTH_WARNINGS", "ZERO_PUBLIC_WORKS_CANDIDATES"} <= codes
    assert payload["monitoring_email"]["ok"] is True
    assert payload["monitoring_email"]["alerts"] == len(payload["monitoring_alerts"])


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


def test_ai_triage_signature_includes_prompt_version(monkeypatch) -> None:
    row = {"row_key": "AUTHORITY:AUTH-1", "title": "Δημοτική οδοποιία"}
    original = ui_server.ai_triage_signature(row)

    monkeypatch.setattr(ui_server, "AI_TRIAGE_PROMPT_VERSION", "next-prompt-version")

    assert ui_server.ai_triage_signature(row) != original


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
    assert "Η αναζήτηση ελέγχει τις συνδεδεμένες πηγές" in INDEX_HTML
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
    assert "linked_eshidis_documents" in APP_JS


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
                        "submission_deadline": "2026-08-20T10:00:00",
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


def test_dashboard_rows_include_why_visible_and_timeline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    ui_server.invalidate_ui_payload_cache()
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
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
    row = ui_server.decorate_tender_row(
        {
            "source": "sqlite",
            "source_label": "ΕΣΗΔΗΣ",
            "row_key": "221744",
            "display_id": "221744",
            "eshidis_id": "221744",
            "title": "Κατασκευή έργου στον Δήμο Πατρέων",
            "authority_name": "Δήμος Πατρέων",
            "budget_with_vat": 1000000,
            "current_deadline_at": "2026-08-20T10:00:00",
            "document_evidence_count": 2,
        }
    )
    monkeypatch.setattr(ui_server, "merged_tender_rows", lambda: [row])
    monkeypatch.setattr(
        ui_server,
        "ai_triage_by_row_key",
        lambda: {
            "221744": {
                "decision": "KEEP_ACTIVE_TENDER",
                "confidence": 0.91,
                "reason": "Ενεργό δημόσιο έργο στην περιοχή ενδιαφέροντος.",
                "keep_for_daily_review": True,
            }
        },
    )
    ui_server.record_notification_sent(
        ui_server.runtime_db_path(),
        row_key="221744",
        channel="email",
        recipient="owner@example.test",
        sent_at="2026-07-22T08:00:00+00:00",
        subject="Tender Radar",
    )

    payload = dashboard_payload(scope="focus", as_of=date(2026, 7, 21), perform_expired_cleanup=False)

    assert payload["summary"]["visible"] == 1
    visible = payload["tenders"][0]["why_visible"]
    profile_fit = payload["tenders"][0]["profile_fit"]
    confidence_band = payload["tenders"][0]["ai_confidence_band"]
    sources = payload["tenders"][0]["project_sources"]
    operations = payload["tenders"][0]["project_operations"]
    timeline = payload["tenders"][0]["project_timeline"]
    assert profile_fit["band"] == "MATCH"
    assert profile_fit["label"] == "Ταιριάζει στο προφίλ"
    assert confidence_band["band"] == "SURE_MATCH"
    assert confidence_band["label"] == "Σίγουρο έργο"
    assert any(item["label"] == "Πηγή" and "ΕΣΗΔΗΣ 221744" in item["text"] for item in visible)
    assert any(item["label"] == "Περιοχή" and "Δήμος Πατρέων" in item["text"] for item in visible)
    assert any(item["label"] == "AI" and "KEEP_ACTIVE_TENDER" in item["text"] for item in visible)
    assert any(item["label"] == "Έγγραφα" and "2" in item["text"] for item in visible)
    assert any(item["label"] == "ΕΣΗΔΗΣ" and item["identifier"] == "221744" for item in sources)
    assert any(item["label"] == "Email" and item["status"] == "sent" for item in operations)
    assert any(item["label"] == "Cleanup" and item["status"] == "scheduled" for item in operations)
    assert [item["label"] for item in timeline] == [
        "Εντοπισμός",
        "Φίλτρο ενδιαφέροντος",
        "ΕΣΗΔΗΣ",
        "Προθεσμία",
        "Έγγραφα",
        "Email",
        "AI έλεγχος",
    ]


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
    ui_server.upsert_verified_tender_link(
        ui_server.runtime_db_path(),
        source_row_key="KIMDIS:26PROC019444361",
        source_identifier="26PROC019444361",
        source_label="ΚΗΜΔΗΣ",
        target_eshidis_id="221744",
        evidence={"official_fetch_ok": True},
    )

    payload = dashboard_payload(scope="focus", as_of=date(2026, 7, 18))

    assert payload["summary"]["total_known"] == 2
    assert payload["summary"]["duplicate_hidden"] == 1
    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["source_label"] == "ΕΣΗΔΗΣ"
    assert payload["tenders"][0]["display_id"] == "221744"
    assert payload["tenders"][0]["project_identity"]["canonical_key"] == "ESHIDIS:221744"
    assert payload["tenders"][0]["project_identity"]["primary_source"] == "ΕΣΗΔΗΣ"
    assert payload["tenders"][0]["source_merge"]["status"] == "CANONICAL_WITH_LINKED_SOURCES"
    assert payload["tenders"][0]["source_merge"]["level"] == "LEVEL_1_OFFICIAL_CROSS_REFERENCE"
    assert any(
        source["label"] == "ΚΗΜΔΗΣ"
        and source["identifier"] == "26PROC019444361"
        and source["role"] == "linked source"
        for source in payload["tenders"][0]["project_sources"]
    )


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
    ui_server.upsert_verified_tender_link(
        ui_server.runtime_db_path(),
        source_row_key="AUTHORITY:AUTH-1234567890abcdef",
        source_identifier="AUTHORITY:AUTH-1234567890abcdef",
        source_label="Φορέας",
        target_eshidis_id="221473",
        evidence={"official_fetch_ok": True},
    )

    payload = dashboard_payload(scope="focus", as_of=date(2026, 7, 18))

    assert payload["summary"]["total_known"] == 2
    assert payload["summary"]["duplicate_hidden"] == 1
    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["source_label"] == "ΕΣΗΔΗΣ"
    assert payload["tenders"][0]["display_id"] == "221473"
    assert payload["tenders"][0]["title"] == "Official ΕΣΗΔΗΣ Πατρών"
    assert payload["tenders"][0]["project_identity"]["canonical_key"] == "ESHIDIS:221473"
    assert payload["tenders"][0]["source_merge"]["status"] == "CANONICAL_WITH_LINKED_SOURCES"
    assert any(
        source["label"] == "Φορέας"
        and source["identifier"] == "AUTHORITY:AUTH-1234567890abcdef"
        and source["merge_level"] == "LEVEL_1_OFFICIAL_CROSS_REFERENCE"
        for source in payload["tenders"][0]["project_sources"]
    )


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
                        "submission_deadline": "2026-08-20T10:00:00",
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


def test_dashboard_hides_same_day_deadlines_after_time() -> None:
    row = {
        "current_deadline_at": "2026-07-21T10:00:00",
    }
    athens = ui_server.dashboard_timezone()

    assert ui_server.dashboard_row_is_active(row, as_of=datetime(2026, 7, 21, 9, 59, tzinfo=athens))
    assert not ui_server.dashboard_row_is_active(row, as_of=datetime(2026, 7, 21, 10, 1, tzinfo=athens))


def test_dashboard_keeps_date_only_deadlines_until_end_of_day() -> None:
    row = {
        "current_deadline_at": "2026-07-21",
    }
    athens = ui_server.dashboard_timezone()

    assert ui_server.dashboard_row_is_active(row, as_of=datetime(2026, 7, 21, 23, 59, tzinfo=athens))
    assert not ui_server.dashboard_row_is_active(row, as_of=datetime(2026, 7, 22, 0, 0, tzinfo=athens))


def test_dashboard_cleanup_deletes_expired_eshidis_downloads(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        "timezone: Europe/Athens\nmunicipalities: []\nregions: []\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "data/tender_radar.sqlite"
    db_path.parent.mkdir()
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
              size_bytes INTEGER,
              sha256 TEXT,
              is_latest INTEGER
            );
            CREATE TABLE documents (attachment_id INTEGER, document_type TEXT, text_sample TEXT);
            CREATE TABLE source_documents (
              id INTEGER PRIMARY KEY,
              row_key TEXT,
              document_url TEXT,
              source_url TEXT,
              local_path TEXT,
              size_bytes INTEGER,
              sha256 TEXT,
              fetched_at TEXT,
              fetch_error TEXT,
              source_signature TEXT,
              metadata_json TEXT DEFAULT '{}'
            );
            """
        )
        pdf_path = tmp_path / "work/download_audit/221566/spec.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"expired")
        connection.execute(
            """
            INSERT INTO tenders (
              id, eshidis_id, title, authority_name, region, budget_with_vat,
              current_deadline_at, status, status_confidence
            ) VALUES (1, '221566', 'Ληγμένο έργο', 'ΔΗΜΟΣ', '', 1000, '2026-07-21T10:00:00', 'UNKNOWN', 0)
            """
        )
        connection.execute(
            "INSERT INTO attachments (tender_id, original_name, local_path, size_bytes, sha256, is_latest) VALUES (1, 'spec.pdf', ?, 7, 'abc', 1)",
            (str(pdf_path),),
        )
        connection.commit()
    finally:
        connection.close()

    payload = dashboard_payload(scope="focus", as_of=datetime(2026, 7, 21, 10, 1, tzinfo=ui_server.dashboard_timezone()))

    assert payload["summary"]["visible"] == 0
    assert payload["summary"]["expired_download_cleanup"]["files_deleted"] == 1
    assert not pdf_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT local_path, size_bytes, sha256 FROM attachments").fetchone()
    finally:
        connection.close()
    assert row == (None, None, None)


def test_dashboard_cleanup_deletes_expired_kimdis_downloads_and_legacy_index(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        "timezone: Europe/Athens\nmunicipalities:\n  - name: Δήμος Πατρέων\n    aliases: [Πάτρα]\nregions: []\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "data/tender_radar.sqlite"
    db_path.parent.mkdir()
    pdf_path = tmp_path / "work/download_audit/kimdis/26PROC000000001/26PROC000000001.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"expired-kimdis")
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_open_proc_candidates": [
                    {
                        "source": "KIMDIS",
                        "record_type": "PROC",
                        "official_id": "26PROC000000001",
                        "title": "Ληγμένο έργο Πάτρας",
                        "authority": "ΔΗΜΟΣ ΠΑΤΡΕΩΝ",
                        "submission_deadline": "2026-07-21T10:00:00",
                        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice/attachment/26PROC000000001",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "status": "SUBMISSION_OPEN_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "work/derived/kimdis_open_proc_documents.json"
    index_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "official_id": "26PROC000000001",
                        "attachment_url": "https://example.test/26PROC000000001.pdf",
                        "local_path": str(pdf_path),
                        "size_bytes": len(b"expired-kimdis"),
                        "sha256": "abc",
                        "document_analysis": {"text_sample": "Πάτρα"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE source_documents (
              id INTEGER PRIMARY KEY,
              row_key TEXT,
              document_url TEXT,
              source_url TEXT,
              local_path TEXT,
              size_bytes INTEGER,
              sha256 TEXT,
              fetched_at TEXT,
              fetch_error TEXT,
              source_signature TEXT,
              metadata_json TEXT DEFAULT '{}'
            );
            CREATE TABLE attachments (
              id INTEGER PRIMARY KEY,
              tender_id INTEGER,
              original_name TEXT,
              local_path TEXT,
              size_bytes INTEGER,
              sha256 TEXT,
              is_latest INTEGER
            );
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
            INSERT INTO source_documents (
              row_key, document_url, source_url, local_path, size_bytes, sha256, metadata_json
            ) VALUES ('KIMDIS:26PROC000000001', 'https://example.test/26PROC000000001.pdf', NULL, ?, 14, 'abc', '{}')
            """,
            (str(pdf_path),),
        )
        connection.commit()
    finally:
        connection.close()

    payload = dashboard_payload(scope="focus", as_of=datetime(2026, 7, 21, 10, 1, tzinfo=ui_server.dashboard_timezone()))

    assert payload["summary"]["visible"] == 0
    assert payload["summary"]["expired_download_cleanup"]["files_deleted"] == 1
    assert not pdf_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT local_path, size_bytes, sha256 FROM source_documents").fetchone()
    finally:
        connection.close()
    assert row == (None, None, None)
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["documents"][0]["local_path"] is None
    assert payload["documents"][0]["size_bytes"] is None
    assert payload["documents"][0]["sha256"] is None


def test_deadline_evidence_extracts_submission_deadline_from_document_text() -> None:
    evidence = ui_server.extract_deadline_evidence_from_text(
        """
        Άρθρο 2.2 Διεύθυνση των εγγράφων της δημόσιας σύμβασης.
        Η καταληκτική προθεσμία υποβολής προσφορών είναι 20/08/2026 ώρα 10:00.
        Η αποσφράγιση θα γίνει σε μεταγενέστερο χρόνο.
        """,
        document_name="Διακήρυξη.pdf",
        document_url="https://example.test/tender.pdf",
        source_url="https://example.test/post",
    )

    assert evidence is not None
    assert evidence["deadline_at"] == "2026-08-20 10:00"
    assert evidence["document_name"] == "Διακήρυξη.pdf"
    assert evidence["evidence_status"] == "DEADLINE_EVIDENCE_FOUND"


def test_dashboard_hides_rows_without_verified_deadline() -> None:
    row = {
        "source_label": "Φορέας",
        "row_key": "AUTHORITY:AUTH-no-deadline",
        "display_id": "AUTH-no-deadline",
        "title": "Διακήρυξη έργου χωρίς επιβεβαιωμένη προθεσμία",
    }

    assert not ui_server.dashboard_row_is_active(row, as_of=date(2026, 7, 19))


def test_dashboard_uses_document_deadline_evidence_for_missing_deadline() -> None:
    row = {
        "source_label": "Φορέας",
        "row_key": "AUTHORITY:AUTH-doc-deadline",
        "display_id": "AUTH-doc-deadline",
        "title": "Διακήρυξη έργου με προθεσμία στα τεύχη",
        "deadline_evidence": {
            "deadline_at": "2026-08-20 10:00",
            "document_name": "Διακήρυξη.pdf",
            "evidence_status": "DEADLINE_EVIDENCE_FOUND",
        },
    }

    assert ui_server.dashboard_row_is_active(row, as_of=date(2026, 7, 19))


def test_admin_audit_separates_missing_deadline_from_expired(tmp_path, monkeypatch) -> None:
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
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps(
            {
                "focus_authority_candidates": [
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-no-date",
                        "title": "Διακήρυξη έργου χωρίς προθεσμία",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://example.test/no-date",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    },
                    {
                        "source": "AUTHORITY",
                        "record_type": "AUTHORITY_WEB",
                        "official_id": "AUTH-expired",
                        "title": "Ληγμένο έργο Πατρέων",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://example.test/expired",
                        "submission_deadline": "2026-01-10T10:00:00",
                        "matched_scopes": ["Δήμος Πατρέων"],
                        "status": "AUTHORITY_DISCOVERY_CANDIDATE",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    audit = ui_server.admin_audit_payload()

    assert audit["summary"]["missing_deadline"] == 1
    assert audit["summary"]["expired"] == 1
    by_category = {row["category"]: row for row in audit["hidden_rows"]}
    assert "NO_DEADLINE_EVIDENCE" in by_category
    assert "ενεργή καταληκτική ημερομηνία" in by_category["NO_DEADLINE_EVIDENCE"]["reason"]
    assert "10-01-2026 10:00" in by_category["EXPIRED"]["reason"]


def test_admin_audit_does_not_mark_out_of_scope_expired_rows_as_hidden(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
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
              size_bytes INTEGER,
              sha256 TEXT,
              is_latest INTEGER
            );
            CREATE TABLE documents (attachment_id INTEGER, document_type TEXT, text_sample TEXT);
            CREATE TABLE source_documents (
              id INTEGER PRIMARY KEY,
              row_key TEXT,
              document_url TEXT,
              source_url TEXT,
              local_path TEXT,
              size_bytes INTEGER,
              sha256 TEXT,
              fetched_at TEXT,
              fetch_error TEXT,
              source_signature TEXT,
              metadata_json TEXT DEFAULT '{}'
            );
            """
        )
        connection.execute(
            """
            INSERT INTO tenders (
              id, eshidis_id, title, authority_name, region, budget_with_vat,
              current_deadline_at, status, status_confidence
            ) VALUES (
              1, '221544', 'Απόφαση δημάρχου για άσχετη σύμβαση',
              'ΓΝΑ ΕΥΑΓΓΕΛΙΣΜΟΣ', NULL, NULL, '2026-07-21T15:00:00', 'UNKNOWN', 0
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    audit = ui_server.admin_audit_payload()

    assert audit["summary"]["expired"] == 0
    assert all(row["display_id"] != "221544" for row in audit["hidden_rows"])


def test_admin_audit_marks_possible_eshidis_duplicate_for_missing_deadline() -> None:
    row = {
        "source_label": "Φορέας",
        "title": "Ενεργειακή αναβάθμιση και δράσεις Εξοικονόμησης Ενέργειας στις Αθλητικές Εγκαταστάσεις του Κλειστού Γυμναστηρίου της Ιεράς Πόλης Μεσολογγίου",
        "authority_name": "Δήμος Ιερής Πόλης Μεσολογγίου",
        "interest_reason": "Δήμος Ιερής Πόλης Μεσολογγίου",
    }
    official = {
        "source_label": "ΕΣΗΔΗΣ",
        "eshidis_id": "221624",
        "display_id": "221624",
        "title": "Ενεργειακή αναβάθμιση ΔΑΚ Μεσολογγίου",
        "authority_name": "ΔΗΜΟΣ ΙΕΡΑΣ ΠΟΛΗΣ ΜΕΣΟΛΟΓΓΙΟΥ, ΔΙΕΥΘΥΝΣΗ ΤΕΧΝΙΚΩΝ ΥΠΗΡΕΣΙΩΝ",
        "current_deadline_at": "27-07-2026 12:00:00",
    }

    match = ui_server.best_possible_eshidis_duplicate(row, [official])

    assert match is not None
    assert match["eshidis_id"] == "221624"
    assert "authority_match" in match["signals"]
    assert "ΕΣΗΔΗΣ 221624" in ui_server.possible_duplicate_reason(row, match, document_count=0)


def test_admin_audit_ui_exposes_missing_deadline_and_mobile_labels() -> None:
    assert "adminMissingDeadlineCount" in INDEX_HTML
    assert "adminDuplicateCandidateCount" in INDEX_HTML
    assert "NO_DEADLINE_EVIDENCE: 'Χωρίς deadline'" in APP_JS
    assert "OUT_OF_SCOPE_SUPPLY_SERVICE: 'Προμήθεια/υπηρεσία'" in APP_JS
    assert 'data-label="Αιτιολογία"' in APP_JS
    assert ".adminTableWrap .adminTable td::before" in STYLES_CSS


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
              size_bytes INTEGER,
              sha256 TEXT,
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
            "INSERT INTO attachments (tender_id, original_name, local_path, size_bytes, sha256, is_latest) VALUES (1, 'spec.pdf', ?, 4, 'linkedabc', 1)",
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
    assert preview["linked_eshidis_documents"][0]["eshidis_id"] == "221473"
    assert preview["linked_eshidis_documents"][0]["view_url"] == "/api/document-file?attachment_id=1"
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


def test_selected_kimdis_fetch_persists_verified_link(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ui_server, "run_kimdis_fetch", lambda official_id: {"ok": True, "official_id": official_id})
    monkeypatch.setattr(ui_server, "kimdis_linked_eshidis_ids", lambda official_id: ["221473"])
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}})
    ui_server.upsert_verified_tender_link(
        ui_server.runtime_db_path(),
        source_row_key="KIMDIS:26PROC019417347",
        source_identifier="26PROC019417347",
        source_label="ΚΗΜΔΗΣ",
        target_eshidis_id="221111",
        verification_status="VERIFIED_ESHIDIS_RESOURCE",
        evidence={"stale": True},
    )

    def fake_run_cli_steps(steps, *, dashboard_scope=None):
        return {"ok": True, "steps": [{"name": step["name"], "returncode": 0} for step in steps], "dashboard": {}}

    monkeypatch.setattr(ui_server, "run_cli_steps", fake_run_cli_steps)

    result = run_selected_fetch("26PROC019417347")
    links = ui_server.list_verified_tender_links(ui_server.runtime_db_path(), source_row_key="KIMDIS:26PROC019417347")

    assert result["ok"] is True
    assert [link.target_eshidis_id for link in links] == ["221473"]
    assert links[0].evidence["verification"] == "manual_selected_fetch"


def test_selected_kimdis_fetch_uses_connected_acts_when_document_has_no_link(monkeypatch) -> None:
    linked_calls = {"count": 0}

    def fake_linked_ids(official_id):
        linked_calls["count"] += 1
        return [] if linked_calls["count"] == 1 else ["221566"]

    monkeypatch.setattr(ui_server, "run_kimdis_fetch", lambda official_id: {"ok": True, "official_id": official_id})
    monkeypatch.setattr(ui_server, "kimdis_linked_eshidis_ids", fake_linked_ids)
    monkeypatch.setattr(
        ui_server,
        "run_kimdis_connected_acts_lookup",
        lambda official_id: {
            "ok": True,
            "official_id": official_id,
            "linked_eshidis_ids": ["221566"],
            "chain_status": "FETCHED",
        },
    )
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}})

    captured = {}

    def fake_run_cli_steps(steps, *, dashboard_scope=None):
        captured["steps"] = steps
        return {"ok": True, "steps": steps, "dashboard": {"scope": dashboard_scope}}

    monkeypatch.setattr(ui_server, "run_cli_steps", fake_run_cli_steps)

    result = run_selected_fetch("26PROC019367864")

    assert result["ok"] is True
    assert result["kimdis_connected_acts"]["chain_status"] == "FETCHED"
    assert result["linked_eshidis_ids"] == ["221566"]
    assert [step["name"] for step in captured["steps"]] == ["fetch_detail_221566", "download_files_221566"]


def test_selected_kimdis_fetch_keeps_review_when_connected_acts_has_no_verified_link(monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "run_kimdis_fetch", lambda official_id: {"ok": True, "official_id": official_id})
    monkeypatch.setattr(ui_server, "kimdis_linked_eshidis_ids", lambda official_id: [])
    monkeypatch.setattr(
        ui_server,
        "run_kimdis_connected_acts_lookup",
        lambda official_id: {
            "ok": True,
            "official_id": official_id,
            "linked_eshidis_ids": [],
            "chain_status": "FETCHED",
        },
    )
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}})

    result = run_selected_fetch("26PROC019367864")

    assert result["ok"] is True
    assert result["linked_eshidis_ids"] == []
    assert result["eshidis_fetch"] is None
    assert result["kimdis_connected_acts"]["chain_status"] == "FETCHED"


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
                        "submission_deadline": "2026-08-20T10:00:00",
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
                        "submission_deadline": "2026-08-20T10:00:00",
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


def test_candidate_enrichment_persists_verified_eshidis_link(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        ui_server,
        "candidate_enrichment_targets",
        lambda scope, limit: (
            [
                {
                    "row_key": "AUTHORITY:AUTH-work",
                    "identifier": "221473",
                    "kind": "Φορέας",
                    "source_url": "https://example.test/work",
                    "source_signature": "sig-verified",
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(
        ui_server,
        "run_selected_fetch",
        lambda identifier: {
            "ok": True,
            "steps": [
                {"name": "fetch_detail_221473", "returncode": 0},
                {"name": "download_files_221473", "returncode": 0},
            ],
            "linked_eshidis_ids": [],
        },
    )
    monkeypatch.setattr(ui_server, "dashboard_payload", lambda scope="focus": {"scope": scope, "summary": {}, "tenders": []})

    result = run_candidate_enrichment(scope="focus", limit=10)
    links = ui_server.list_verified_tender_links(ui_server.runtime_db_path(), source_row_key="AUTHORITY:AUTH-work")

    assert result["summary"]["verified_eshidis_links"] == 1
    assert links[0].target_eshidis_id == "221473"
    assert links[0].verification_status == "VERIFIED_ESHIDIS_RESOURCE"
    assert links[0].evidence["identifier_used"] == "221473"


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
    assert "finalResult.ok !== false && !finalResult.skipped" in APP_JS
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
                        "submission_deadline": "2026-08-20T10:00:00",
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

    assert dashboard_payload(scope="focus", user_email="owner@example.test")["summary"]["visible"] == 1
    result = ui_server.dismiss_tender(row_key, user_email="owner@example.test")
    payload = dashboard_payload(scope="focus", user_email="owner@example.test")
    other_payload = dashboard_payload(scope="focus", user_email="other@example.test")

    assert result["ok"] is True
    assert payload["summary"]["visible"] == 0
    assert payload["summary"]["ignored"] == 1
    assert other_payload["summary"]["visible"] == 1
    assert other_payload["summary"]["ignored"] == 0


def test_user_interest_profile_filters_dashboard_for_current_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-asphalt",
                "title": "Ασφαλτόστρωση οδού Δήμου Πατρέων",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/asphalt",
                "budget_with_vat": "120.000,00",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            },
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-playground",
                "title": "Αναβάθμιση παιδικής χαράς Δήμου Πατρέων",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/playground",
                "budget_with_vat": "30.000,00",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            },
        ],
    )

    saved = ui_server.update_user_interest_profile(
        "owner@example.test",
        {"include_keywords": "ασφαλτόστρωση\nοδοποιία", "min_budget": "50000"},
    )

    owner_payload = dashboard_payload(scope="focus", user_email="owner@example.test")
    other_payload = dashboard_payload(scope="focus", user_email="other@example.test")

    assert saved["active"] is True
    assert owner_payload["summary"]["visible"] == 1
    assert owner_payload["profile"]["user_interest_active"] is True
    assert owner_payload["tenders"][0]["display_id"] == "AUTH-asphalt"
    assert owner_payload["tenders"][0]["profile_fit"]["band"] == "USER_MATCH"
    assert "ασφαλτόστρωση" in owner_payload["tenders"][0]["profile_fit"]["reason"]
    assert other_payload["summary"]["visible"] == 2
    assert other_payload["profile"]["user_interest_active"] is False


def test_user_interest_profile_exclude_keyword_is_user_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-asphalt",
                "title": "Ασφαλτόστρωση οδού Δήμου Πατρέων",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/asphalt",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            }
        ],
    )

    ui_server.update_user_interest_profile("owner@example.test", {"exclude_keywords": ["ασφαλτόστρωση"]})

    assert dashboard_payload(scope="focus", user_email="owner@example.test")["summary"]["visible"] == 0
    assert dashboard_payload(scope="focus", user_email="other@example.test")["summary"]["visible"] == 1


def test_user_interest_profile_category_filter_is_user_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-asphalt",
                "title": "Ασφαλτόστρωση οδού Δήμου Πατρέων",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/asphalt",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            },
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-playground",
                "title": "Αναβάθμιση παιδικής χαράς Δήμου Πατρέων",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/playground",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            },
        ],
    )
    (tmp_path / "config/public_works_taxonomy.yml").write_text(
        """
version: 1
confidence:
  strong: 0.85
categories:
  - id: road_works
    label: "Οδοποιία / οδικά έργα"
    positive_weight: 2
    signals:
      strong_terms: ["ασφαλτόστρωση"]
  - id: public_space
    label: "Αναπλάσεις / κοινόχρηστοι χώροι"
    positive_weight: 2
    signals:
      strong_terms: ["παιδική χαρά"]
""",
        encoding="utf-8",
    )

    saved = ui_server.update_user_interest_profile("owner@example.test", {"category_ids": ["road_works"]})
    owner_payload = dashboard_payload(scope="focus", user_email="owner@example.test")
    other_payload = dashboard_payload(scope="focus", user_email="other@example.test")

    assert saved["active"] is True
    assert saved["profile"]["category_ids"] == ["road_works"]
    assert saved["category_options"][0]["label"] == "Οδοποιία / οδικά έργα"
    assert owner_payload["summary"]["visible"] == 1
    assert owner_payload["tenders"][0]["display_id"] == "AUTH-asphalt"
    assert "Οδοποιία / οδικά έργα" in owner_payload["tenders"][0]["profile_fit"]["reason"]
    assert other_payload["summary"]["visible"] == 2
    assert other_payload["profile"]["user_interest_active"] is False


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
                        "submission_deadline": "2026-08-20T10:00:00",
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
                            "submission_deadline": "2026-08-20T10:00:00",
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
    assert payload["tenders"][0]["ai_confidence_band"]["band"] == "SURE_MATCH"

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
    assert audit["hidden_rows"][0]["category"] == "AI_DROP_ADMIN"
    assert audit["hidden_rows"][0]["ai_confidence_band"]["band"] == "SURE_DROP"
    assert audit["hidden_rows"][0]["ai_confidence_band"]["label"] == "Σίγουρα άσχετο"
    assert audit["hidden_rows"][0]["profile_fit"]["label"] == "Ταιριάζει στο προφίλ"
    assert audit["hidden_rows"][0]["restorable"] is True
    assert "διοικητική" in audit["hidden_rows"][0]["reason"]
    assert "διοικητικό" in audit["hidden_rows"][0]["reason"]
    assert audit["summary"]["review_queue_total"] == 1
    assert audit["review_queue"][0]["review_priority"] == "LOW"

    restored = ui_server.restore_admin_row(row_key="AUTHORITY:AUTH-drop", reason="είναι ενεργό έργο")

    assert restored["ok"] is True
    payload = dashboard_payload(scope="focus")
    assert payload["summary"]["visible"] == 1
    assert payload["tenders"][0]["triage_override"]["action"] == "FORCE_KEEP"


def test_admin_review_feedback_confirms_drop_without_removing_audit_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    ui_server.invalidate_ui_payload_cache()
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-drop",
                "title": "Διακήρυξη έργου Πατρών για έλεγχο",
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

    before = ui_server.admin_audit_payload()
    assert before["summary"]["review_queue_total"] == 1

    result = ui_server.admin_review_feedback(
        row_key="AUTHORITY:AUTH-drop",
        action="CONFIRM_DROP",
        reason="σωστά κόπηκε",
        actor_email="owner@example.test",
    )

    assert result["ok"] is True
    assert result["action"] == "CONFIRM_DROP"
    assert result["admin"]["summary"]["review_queue_total"] == 0
    assert result["admin"]["summary"]["ai_hidden"] == 1
    hidden = result["admin"]["hidden_rows"][0]
    assert hidden["feedback_action"] == "CONFIRM_DROP"
    assert hidden["feedback_reason"] == "σωστά κόπηκε"


def test_admin_review_feedback_is_user_scoped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    ui_server.invalidate_ui_payload_cache()
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-user-scope",
                "title": "Διακήρυξη έργου Πατρών για user scope",
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
                        "row_key": "AUTHORITY:AUTH-user-scope",
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

    owner_before = ui_server.admin_audit_payload(user_email="owner@example.test")
    other_before = ui_server.admin_audit_payload(user_email="other@example.test")
    assert owner_before["summary"]["review_queue_total"] == 1
    assert other_before["summary"]["review_queue_total"] == 1

    ui_server.admin_review_feedback(
        row_key="AUTHORITY:AUTH-user-scope",
        action="CONFIRM_DROP",
        reason="σωστά κόπηκε για μένα",
        actor_email="owner@example.test",
        user_email="owner@example.test",
    )

    assert ui_server.admin_audit_payload(user_email="owner@example.test")["summary"]["review_queue_total"] == 0
    assert ui_server.admin_audit_payload(user_email="other@example.test")["summary"]["review_queue_total"] == 1
    assert dashboard_payload(scope="focus", user_email="owner@example.test")["summary"]["visible"] == 0
    assert dashboard_payload(scope="focus", user_email="other@example.test")["summary"]["visible"] == 0

    ui_server.admin_review_feedback(
        row_key="AUTHORITY:AUTH-user-scope",
        action="FORCE_KEEP",
        reason="το θέλω",
        actor_email="other@example.test",
        user_email="other@example.test",
    )

    owner_payload = dashboard_payload(scope="focus", user_email="owner@example.test")
    other_payload = dashboard_payload(scope="focus", user_email="other@example.test")
    assert owner_payload["summary"]["visible"] == 0
    assert other_payload["summary"]["visible"] == 1
    assert other_payload["tenders"][0]["triage_override"]["action"] == "FORCE_KEEP"
    assert other_payload["tenders"][0]["triage_override"]["scope"] == "user"


def test_admin_false_negative_review_queue_prioritizes_ai_drops_with_public_work_terms() -> None:
    hidden_rows = [
        {
            "row_key": "AUTHORITY:AUTH-road",
            "category": "AI_DROP_SUPPLY_SERVICE",
            "display_id": "AUTH-road",
            "source_label": "Φορέας",
            "title": "Συντήρηση οδικού δικτύου και ασφαλτοστρώσεις",
            "reason": "AI έλεγχος: προμήθεια ή υπηρεσία εκτός δημοσίων έργων.",
            "ai_decision": "DROP_OUT_OF_SCOPE_SUPPLY_SERVICE",
            "ai_confidence": 0.95,
            "audit_at": "2026-07-19T09:00:00+00:00",
        },
        {
            "row_key": "AUTHORITY:AUTH-admin",
            "category": "AI_DROP_ADMIN",
            "display_id": "AUTH-admin",
            "source_label": "Φορέας",
            "title": "Απόφαση δημάρχου",
            "reason": "AI έλεγχος: διοικητική πράξη.",
            "ai_decision": "DROP_ADMIN",
            "ai_confidence": 0.95,
            "audit_at": "2026-07-19T10:00:00+00:00",
        },
    ]

    queue = ui_server.admin_false_negative_review_queue(hidden_rows)

    assert [row["row_key"] for row in queue] == ["AUTHORITY:AUTH-road", "AUTHORITY:AUTH-admin"]
    assert queue[0]["review_priority"] == "HIGH"
    assert "λέξεις δημοσίων έργων" in queue[0]["review_reason"]
    assert queue[1]["review_priority"] == "LOW"


def test_admin_false_negative_review_queue_skips_obvious_supply_service_rows() -> None:
    hidden_rows = [
        {
            "row_key": "AUTHORITY:AUTH-fuel",
            "category": "NO_DEADLINE_EVIDENCE",
            "display_id": "AUTH-fuel",
            "source_label": "Φορέας",
            "title": "Διακήρυξη για την Προμήθεια Καυσίμων και Λιπαντικών του Δήμου",
            "reason": "Δεν τεκμηριώθηκε ενεργή προθεσμία.",
            "audit_at": "2026-07-19T09:00:00+00:00",
        },
        {
            "row_key": "AUTHORITY:AUTH-telemetry",
            "category": "NO_DEADLINE_EVIDENCE",
            "display_id": "AUTH-telemetry",
            "source_label": "Φορέας",
            "title": "Προμήθεια, εγκατάσταση και θέση σε λειτουργία συστήματος τηλεελέγχου / τηλεχειρισμού",
            "reason": "Δεν τεκμηριώθηκε ενεργή προθεσμία.",
            "audit_at": "2026-07-19T10:00:00+00:00",
        },
        {
            "row_key": "AUTHORITY:AUTH-students",
            "category": "NO_DEADLINE_EVIDENCE",
            "display_id": "AUTH-students",
            "source_label": "Φορέας",
            "title": "Πρόσκληση διαγωνισμού για την παροχή υπηρεσιών Μεταφοράς μαθητών",
            "reason": "Δεν τεκμηριώθηκε ενεργή προθεσμία.",
            "audit_at": "2026-07-19T11:00:00+00:00",
        },
    ]

    assert ui_server.admin_false_negative_review_queue(hidden_rows) == []
    assert "καθαρά προμήθεια καυσίμων" in ui_server.obvious_out_of_scope_supply_service_reason(hidden_rows[0])


def test_obvious_supply_service_filter_keeps_road_maintenance_for_review() -> None:
    row = {
        "title": (
            "Ηλεκτρονικός Ανοικτός Διαγωνισμός για Χειμερινή Συντήρηση Οδικού Δικτύου "
            "αρμοδιότητας Π.Ε. Φωκίδας"
        ),
        "reason": "Δεν τεκμηριώθηκε ενεργή προθεσμία.",
    }

    assert ui_server.obvious_out_of_scope_supply_service_reason(row) is None


def test_admin_audit_hidden_rows_are_recent_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-ai-old",
                "title": "Παλαιότερη AI απόρριψη έργου οδοποιίας Πατρών",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/ai-old",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            },
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-manual-new",
                "title": "Νεότερη χειροκίνητη απόρριψη έργου οδοποιίας Πατρών",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/manual-new",
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            },
        ],
    )
    (tmp_path / "work/reports/ai_triage_report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-19T09:00:00+00:00",
                "rows": [
                    {
                        "row_key": "AUTHORITY:AUTH-ai-old",
                        "ai": {
                            "decision": "DROP_ADMIN",
                            "confidence": 0.9,
                            "reason": "διοικητικό",
                            "eshidis_id_candidates": [],
                            "keep_for_daily_review": False,
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ui_server.dismiss_tender_in_db(
        tmp_path / "data/tender_radar.sqlite",
        row_key="AUTHORITY:AUTH-manual-new",
        ignored_at="2026-07-19T12:00:00+00:00",
    )

    audit = ui_server.admin_audit_payload()

    assert [row["category"] for row in audit["hidden_rows"][:2]] == ["DISMISSED", "AI_DROP_ADMIN"]
    assert [row["display_id"] for row in audit["hidden_rows"][:2]] == ["AUTH-manual-new", "AUTH-ai-old"]
    assert [row["audit_at"] for row in audit["hidden_rows"][:2]] == [
        "2026-07-19T12:00:00+00:00",
        "2026-07-19T09:00:00+00:00",
    ]


def test_admin_audit_timestamp_normalizes_epoch_ms_and_ignores_placeholders() -> None:
    assert ui_server.admin_audit_timestamp_text("1784246400000") == "2026-07-17T00:00:00+00:00"
    assert ui_server.admin_audit_timestamp_text("9999") == ""


def test_admin_audit_deterministic_rows_keep_first_hidden_time(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    write_patras_authority_fixture(
        tmp_path,
        [
            {
                "source": "AUTHORITY",
                "record_type": "AUTHORITY_WEB",
                "official_id": "AUTH-no-deadline",
                "title": "Διακήρυξη έργου οδοποιίας χωρίς parseable deadline",
                "authority": "Δήμος Πατρέων",
                "source_url": "https://e-patras.gr/el/no-deadline",
                "submission_deadline": None,
                "matched_scopes": ["Δήμος Πατρέων"],
                "match_notes": [],
                "status": "AUTHORITY_DISCOVERY_CANDIDATE",
            }
        ],
    )

    monkeypatch.setattr(ui_server, "utc_now_iso", lambda: "2026-07-19T10:00:00+00:00")
    first = ui_server.admin_audit_payload()
    monkeypatch.setattr(ui_server, "utc_now_iso", lambda: "2026-07-19T12:00:00+00:00")
    second = ui_server.admin_audit_payload()

    assert first["hidden_rows"][0]["category"] == "NO_DEADLINE_EVIDENCE"
    assert first["hidden_rows"][0]["audit_at"] == "2026-07-19T10:00:00+00:00"
    assert second["hidden_rows"][0]["audit_at"] == "2026-07-19T10:00:00+00:00"


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

    ui_server.dismiss_tender(row_key, user_email="owner@example.test")
    assert dashboard_payload(scope="focus", user_email="owner@example.test")["summary"]["visible"] == 0
    assert dashboard_payload(scope="focus", user_email="other@example.test")["summary"]["visible"] == 1
    assert ui_server.admin_audit_payload()["summary"]["dismissed"] == 1

    ui_server.restore_admin_row(row_key=row_key, reason="κατά λάθος")

    assert dashboard_payload(scope="focus", user_email="owner@example.test")["summary"]["visible"] == 1
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
                        "submission_deadline": "2026-08-20T10:00:00",
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
                        "submission_deadline": "2026-08-20T10:00:00",
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


def test_dashboard_replaces_verified_non_eshidis_row_with_official_eshidis(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    ui_server.upsert_verified_tender_link(
        ui_server.runtime_db_path(),
        source_row_key="KIMDIS:26PROC000000001",
        source_identifier="26PROC000000001",
        source_label="ΚΗΜΔΗΣ",
        source_url="https://example.test/kimdis",
        target_eshidis_id="221744",
        evidence={"official_fetch_ok": True},
    )
    rows = [
        {
            "source": "sqlite",
            "source_label": "ΕΣΗΔΗΣ",
            "row_key": "221744",
            "display_id": "221744",
            "eshidis_id": "221744",
            "title": "Ίδιο έργο",
            "current_deadline_at": "20-08-2026 10:00:00",
        },
        {
            "source": "kimdis",
            "source_label": "ΚΗΜΔΗΣ",
            "row_key": "KIMDIS:26PROC000000001",
            "display_id": "26PROC000000001",
            "title": "Ίδιο έργο",
            "linked_eshidis_ids": ["221744"],
        },
    ]

    kept, hidden = ui_server.suppress_linked_eshidis_duplicates(rows)

    assert [row["source_label"] for row in kept] == ["ΕΣΗΔΗΣ"]
    assert kept[0]["verified_source_links"][0]["source_row_key"] == "KIMDIS:26PROC000000001"
    assert hidden[0]["verified_eshidis_ids"] == ["221744"]
    assert hidden[0]["verified_eshidis_link_status"] == "REPLACED_BY_OFFICIAL_ESHIDIS"


def test_dashboard_keeps_unverified_non_eshidis_rows_visible(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    rows = [
        {
            "source": "sqlite",
            "source_label": "ΕΣΗΔΗΣ",
            "row_key": "221744",
            "display_id": "221744",
            "eshidis_id": "221744",
            "title": "Έργο Ναυπάκτου",
            "current_deadline_at": "20-08-2026 10:00:00",
        },
        {
            "source": "authority",
            "source_label": "Φορέας",
            "row_key": "AUTHORITY:AUTH-work",
            "display_id": "AUTH-work",
            "title": "Έργο Ναυπάκτου",
            "linked_eshidis_ids": ["221744"],
        },
    ]

    kept, hidden = ui_server.suppress_linked_eshidis_duplicates(rows)

    assert hidden == []
    assert [row["source_label"] for row in kept] == ["ΕΣΗΔΗΣ", "Φορέας"]
    assert kept[1]["verified_eshidis_link_status"] == "NO_VERIFIED_ESHIDIS_LINK"


def test_dashboard_hides_strong_linked_duplicate_without_persisted_link(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    rows = [
        {
            "source": "sqlite",
            "source_label": "ΕΣΗΔΗΣ",
            "row_key": "221566",
            "display_id": "221566",
            "eshidis_id": "221566",
            "title": "ΛΙΜΕΝΙΚΗ ΕΓΚΑΤΑΣΤΑΣΗ ΕΞΥΠΗΡΕΤΗΣΗΣ ΣΚΑΦΩΝ ΣΤΗ ΘΕΣΗ ΨΑΝΗ ΝΑΥΠΑΚΤΟΥ",
            "authority_name": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ, ΔΙΕΥΘΥΝΣΗ ΤΕΧΝΙΚΩΝ ΥΠΗΡΕΣΙΩΝ",
            "budget_with_vat": 4216000.0,
            "current_deadline_at": "21-07-2026 10:00:00",
        },
        {
            "source": "kimdis",
            "source_label": "ΚΗΜΔΗΣ",
            "row_key": "KIMDIS:26PROC019367864",
            "display_id": "26PROC019367864",
            "title": "ΛΙΜΕΝΙΚΗ ΕΓΚΑΤΑΣΤΑΣΗ ΕΞΥΠΗΡΕΤΗΣΗΣ ΣΚΑΦΩΝ ΣΤΗ ΘΕΣΗ ΨΑΝΗ ΝΑΥΠΑΚΤΟΥ",
            "authority_name": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ",
            "budget_with_vat": "4.216.000,00 EUR",
            "current_deadline_at": "21-07-2026 10:00",
            "linked_eshidis_ids": ["221566"],
        },
    ]

    kept, hidden = ui_server.suppress_linked_eshidis_duplicates(rows)

    assert [row["source_label"] for row in kept] == ["ΕΣΗΔΗΣ"]
    assert hidden[0]["display_id"] == "26PROC019367864"
    assert hidden[0]["verified_eshidis_link_status"] == "STRONG_LINKED_ESHIDIS_DUPLICATE"
    assert hidden[0]["duplicate_reason"] == "Strong linked duplicate of ESHIDIS 221566"


def test_dashboard_row_uses_linked_official_eshidis_deadline_when_source_deadline_is_missing() -> None:
    row = {
        "source_label": "Φορέας",
        "row_key": "AUTHORITY:AUTH-6e565827798444b6",
        "display_id": "AUTH-6e565827798444b6",
        "title": "ΔΗΜΟΤΙΚΗ ΟΔΟΠΟΙΙΑ Δ.ΕΥΠΑΛΙΟΥ",
        "linked_eshidis_ids": ["217922"],
    }

    assert not ui_server.dashboard_row_is_active(
        row,
        as_of=date(2026, 7, 19),
        official_deadlines={"217922": "16-02-2026 15:00:00"},
    )
    assert ui_server.dashboard_row_is_active(
        row,
        as_of=date(2026, 1, 10),
        official_deadlines={"217922": "16-02-2026 15:00:00"},
    )


def test_dashboard_does_not_deduplicate_by_title_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    rows = [
        {
            "source": "sqlite",
            "source_label": "ΕΣΗΔΗΣ",
            "row_key": "221744",
            "display_id": "221744",
            "eshidis_id": "221744",
            "title": "Αναπλάσεις ΔΕ Ναυπάκτου",
            "current_deadline_at": "20-08-2026 10:00:00",
        },
        {
            "source": "authority",
            "source_label": "Φορέας",
            "row_key": "AUTHORITY:AUTH-other",
            "display_id": "AUTH-other",
            "title": "Αναπλάσεις ΔΕ Ναυπάκτου",
        },
    ]

    kept, hidden = ui_server.suppress_linked_eshidis_duplicates(rows)

    assert hidden == []
    assert len(kept) == 2


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


def test_backfill_discovery_skips_when_sources_unchanged_and_previous_window_complete(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "config/locations.yml").write_text(
        "timezone: Europe/Athens\nmunicipalities: []\nregions: []\n",
        encoding="utf-8",
    )
    (tmp_path / "work/reports/expanded_discovery_report.json").write_text(
        json.dumps({"focus_authority_candidates": [], "focus_open_proc_candidates": []}),
        encoding="utf-8",
    )
    append_discovery_run(
        tmp_path / "work/derived/discovery_runs.json",
        {
            "run_id": "previous",
            "success": True,
            "watermark": {"complete": True},
        },
    )
    fingerprint = {"ok": True, "hash": "same", "sources": [], "errors": []}
    ui_server.save_source_fingerprint(fingerprint)
    monkeypatch.setattr(ui_server, "quick_source_fingerprint", lambda timeout_seconds=8: fingerprint)

    def fail_run_cli_process(args, *, timeout):
        raise AssertionError("complete unchanged backfill should be skipped")

    monkeypatch.setattr(ui_server, "run_cli_process", fail_run_cli_process)

    result = run_discovery_search(limit=100, backfill=True)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["skip_reason"] == "SKIPPED_UNCHANGED_BACKFILL_COMPLETE"
    assert result["steps"] == []


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
