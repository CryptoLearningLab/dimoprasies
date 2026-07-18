from pathlib import Path
import time

import tender_radar.ui_server as ui_server
from tender_radar.ui_server import (
    APP_JS,
    DEFAULT_KIMDIS_DISCOVERY_PAGES,
    INDEX_HTML,
    content_type_for_path,
    dashboard_payload,
    document_zip_bytes,
    discovery_search_steps,
    format_budget,
    interest_reason,
    kimdis_document_file_path,
    kimdis_document_preview_payload,
    parse_budget_from_row_text,
    preview_kind,
    run_selected_fetch,
    short_text_sample,
    start_job,
    focus_term_matches,
)


def test_report_json_content_type_includes_utf8_charset() -> None:
    assert content_type_for_path(Path("candidates.json")) == "application/json; charset=utf-8"


def test_report_markdown_content_type_includes_utf8_charset() -> None:
    assert content_type_for_path(Path("candidates.md")) == "text/markdown; charset=utf-8"


def test_ui_has_separate_id_source_columns_and_kimdis_tool_input() -> None:
    assert "<th>Α/Α</th>" in INDEX_HTML
    assert "<th>Πηγή</th>" in INDEX_HTML
    assert "Α/Α / Πηγή" not in INDEX_HTML
    assert 'id="kimdisInput"' in INDEX_HTML
    assert 'id="kimdisFetchBtn"' in INDEX_HTML


def test_ui_uses_safer_discovery_defaults() -> None:
    assert 'value="100"' in INDEX_HTML
    steps = discovery_search_steps(limit=100, as_of_date="2026-07-17")
    expanded_args = steps[1]["args"]
    assert expanded_args[expanded_args.index("--kimdis-pages") + 1] == str(DEFAULT_KIMDIS_DISCOVERY_PAGES)
    assert DEFAULT_KIMDIS_DISCOVERY_PAGES == 20


def test_dashboard_actions_use_fetch_and_zip_not_preview_buttons() -> None:
    assert "fetchTender" in APP_JS
    assert "/api/fetch-selected" in APP_JS
    assert "/api/document-zip" in APP_JS
    assert "previewTender" not in APP_JS


def test_dashboard_rows_select_preview_on_click() -> None:
    assert "selectedRow" in APP_JS
    assert "highlightSelectedRow" in APP_JS
    assert "row.addEventListener('click', () => selectTender(row.dataset.key, false))" in APP_JS
    assert "event.stopPropagation()" in APP_JS


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


def test_dashboard_exposes_local_kimdis_preview_and_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_server, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "work/reports").mkdir(parents=True)
    (tmp_path / "work/derived").mkdir(parents=True)
    pdf_path = tmp_path / "work/download_audit/kimdis/26PROC000000001/26PROC000000001.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF")
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


def test_discovery_search_steps_run_eshidis_then_expanded_kimdis() -> None:
    steps = discovery_search_steps(limit=25, as_of_date="2026-07-17")

    assert [step["name"] for step in steps] == ["eshidis_discover", "expanded_report"]
    assert steps[0]["args"][:2] == ["sources", "discover-active"]
    assert steps[1]["args"][:2] == ["sources", "expanded-report"]
    assert "--eshidis-candidates" in steps[1]["args"]
    assert "work/reports/expanded_discovery_report.json" in steps[1]["args"]
    assert "2026-07-17" in steps[1]["args"]
    assert steps[1]["args"][steps[1]["args"].index("--kimdis-pages") + 1] == "20"


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
