import hashlib
import json
from email.message import Message
from unittest.mock import patch

from tender_radar.sources.kimdis_fetch import (
    FETCHED_STATUS,
    fetch_kimdis_open_proc_candidates,
    kimdis_document_index,
    render_kimdis_fetch_markdown,
    write_kimdis_document_index,
)


def test_fetch_kimdis_open_proc_downloads_attachment_with_metadata(tmp_path) -> None:
    expanded_report = tmp_path / "expanded.json"
    expanded_report.write_text(
        json.dumps(
            {
                "focus_open_proc_candidates": [
                    {
                        "source": "KIMDIS",
                        "record_type": "PROC",
                        "official_id": "26PROC019417347",
                        "title": "Αναπλάσεις ΔΕ Ναυπάκτου",
                        "authority": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ",
                        "budget": "1000",
                        "submission_deadline": "2026-08-01T10:00:00",
                        "source_url": "https://example.test/source",
                        "attachment_url": "https://example.test/attachment",
                        "matched_scopes": ["Δήμος Ναυπακτίας"],
                        "status": "SUBMISSION_OPEN_CANDIDATE",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    body = b"%PDF-1.4 fake"

    class Response:
        headers = Message()

        def __init__(self) -> None:
            self.headers["Content-Type"] = "application/pdf"
            self.headers["Content-Disposition"] = "attachment; filename*=UTF-8''%CE%94%CE%B9%CE%B1%CE%BA%CE%AE%CF%81%CF%85%CE%BE%CE%B7.pdf"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return body

    with patch("tender_radar.sources.kimdis_fetch.urlopen", return_value=Response()) as mocked_urlopen:
        report = fetch_kimdis_open_proc_candidates(
            expanded_report_path=expanded_report,
            download_dir=tmp_path / "downloads",
        )

    result = report["shortlist"][0]
    assert mocked_urlopen.call_count == 1
    assert report["summary"]["candidates_checked"] == 1
    assert report["summary"]["downloaded"] == 1
    assert result["verification_status"] == FETCHED_STATUS
    assert result["sha256"] == hashlib.sha256(body).hexdigest()
    assert result["size_bytes"] == len(body)
    assert result["local_path"].endswith("Διακήρυξη.pdf")
    assert result["document_analysis"]["document_type"] == "tender_declaration"
    assert result["document_analysis"]["extraction_status"] in {"EXTRACTION_FAILED", "NO_TEXT_FOUND"}


def test_fetch_kimdis_open_proc_keeps_repeated_titles_separate(tmp_path) -> None:
    expanded_report = tmp_path / "expanded.json"
    expanded_report.write_text(
        json.dumps(
            {
                "focus_open_proc_candidates": [
                    _candidate("26PROC000000001", "https://example.test/1"),
                    _candidate("26PROC000000002", "https://example.test/2"),
                    {**_candidate("26PROC000000003", "https://example.test/3"), "status": "SUBMISSION_EXPIRED_CANDIDATE"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class Response:
        headers = Message()

        def __init__(self) -> None:
            self.headers["Content-Type"] = "application/octet-stream"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"attachment"

    with patch("tender_radar.sources.kimdis_fetch.urlopen", return_value=Response()):
        report = fetch_kimdis_open_proc_candidates(
            expanded_report_path=expanded_report,
            download_dir=tmp_path / "downloads",
        )

    assert report["summary"]["candidates_checked"] == 2
    assert [item["official_id"] for item in report["shortlist"]] == ["26PROC000000001", "26PROC000000002"]
    assert report["deduplication"]["title_only_merge"] is False


def test_fetch_kimdis_open_proc_marks_document_evidence_from_text(tmp_path) -> None:
    config_path = tmp_path / "sources.yml"
    config_path.write_text(
        """
version: 1
global_sources: []
collection_order: []
rules: []
scopes:
  - id: nafpaktia
    name: "Δήμος Ναυπακτίας"
    aliases: ["Ναυπακτία"]
    sources: []
""",
        encoding="utf-8",
    )
    expanded_report = tmp_path / "expanded.json"
    expanded_report.write_text(
        json.dumps({"focus_open_proc_candidates": [_candidate("26PROC000000001", "https://example.test/1")]}, ensure_ascii=False),
        encoding="utf-8",
    )

    class Response:
        headers = Message()

        def __init__(self) -> None:
            self.headers["Content-Type"] = "application/xml"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return "<root>ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ έργο στη Ναυπακτία</root>".encode("utf-8")

    with patch("tender_radar.sources.kimdis_fetch.urlopen", return_value=Response()):
        report = fetch_kimdis_open_proc_candidates(
            expanded_report_path=expanded_report,
            download_dir=tmp_path / "downloads",
            sources_config_path=config_path,
            text_dir=tmp_path / "text",
        )

    evidence = report["shortlist"][0]["document_evidence"]
    assert report["summary"]["document_evidence_found"] == 1
    assert report["shortlist"][0]["text_path"].endswith("26PROC000000001.txt")
    assert evidence["evidence_status"] == "DOCUMENT_EVIDENCE_FOUND"
    assert evidence["authority_match"] == "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ"
    assert evidence["scope_alias_matches"]


def test_kimdis_document_index_preserves_required_metadata(tmp_path) -> None:
    report = {
        "checked_at": "2026-07-17T00:00:00+00:00",
        "expanded_report_path": "work/reports/expanded_discovery_report.json",
        "summary": {"candidates_checked": 1},
        "deduplication": {"title_only_merge": False},
        "status_note": "candidate-only",
        "shortlist": [
            {
                "official_id": "26PROC000000001",
                "title": "Έργο",
                "authority": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ",
                "budget": "1000",
                "submission_deadline": "2026-08-01T10:00:00",
                "source_url": "https://example.test/source",
                "attachment_url": "https://example.test/attachment",
                "matched_scopes": ["Δήμος Ναυπακτίας"],
                "candidate_status": "SUBMISSION_OPEN_CANDIDATE",
                "verification_status": "ATTACHMENT_ALREADY_FETCHED_PENDING_DOCUMENT_REVIEW",
                "retrieved_at": "2026-07-17T00:00:00+00:00",
                "local_path": "work/download_audit/kimdis/26PROC000000001/26PROC000000001.pdf",
                "original_filename": "26PROC000000001.pdf",
                "content_type": "application/pdf",
                "size_bytes": 123,
                "sha256": "abc",
                "text_path": "work/extracted_text/kimdis/26PROC000000001.txt",
                "document_analysis": {"document_type": "other", "text_sample": "sample"},
                "document_evidence": {"evidence_status": "DOCUMENT_EVIDENCE_FOUND"},
            }
        ],
    }

    index_path = tmp_path / "index.json"
    index = write_kimdis_document_index(report, index_path)
    reloaded = kimdis_document_index(report)

    assert index_path.exists()
    assert index["documents"][0]["official_id"] == "26PROC000000001"
    assert index["documents"][0]["sha256"] == "abc"
    assert index["documents"][0]["candidate_status"] == "SUBMISSION_OPEN_CANDIDATE"
    assert reloaded["deduplication"]["title_only_merge"] is False


def test_render_kimdis_fetch_markdown_states_candidate_only() -> None:
    markdown = render_kimdis_fetch_markdown(
        {
            "checked_at": "2026-07-17T00:00:00+00:00",
            "expanded_report_path": "work/reports/expanded_discovery_report.json",
            "summary": {"candidates_checked": 0, "downloaded": 0, "failed": 0},
            "shortlist": [],
        }
    )

    assert "KIMDIS Open PROC Fetch Report" in markdown
    assert "VERIFIED_ACTIVE" in markdown
    assert "title-only merge is disabled" in markdown


def _candidate(official_id: str, attachment_url: str) -> dict[str, object]:
    return {
        "source": "KIMDIS",
        "record_type": "PROC",
        "official_id": official_id,
        "title": "Αναπλάσεις ΔΕ Ναυπάκτου",
        "authority": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ",
        "budget": "1000",
        "submission_deadline": "2026-08-01T10:00:00",
        "source_url": "https://example.test/source",
        "attachment_url": attachment_url,
        "matched_scopes": ["Δήμος Ναυπακτίας"],
        "status": "SUBMISSION_OPEN_CANDIDATE",
    }
