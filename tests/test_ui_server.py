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
    run_discovery_search,
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
                        "title": "ΠΡΟΓΡΑΜΜΑ ΕΚΛΟΓΩΝ",
                        "authority": "Δήμος Πατρέων",
                        "source_url": "https://e-patras.gr/el/admin",
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
