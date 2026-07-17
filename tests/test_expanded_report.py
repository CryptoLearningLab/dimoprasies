from datetime import date
import json
from unittest.mock import patch

from tender_radar.sources.expanded_report import build_expanded_report, render_expanded_report_markdown


def test_expanded_report_matches_focus_alias_from_eshidis(tmp_path) -> None:
    config_path = tmp_path / "sources.yml"
    config_path.write_text(
        """
version: 1
global_sources: []
collection_order: []
rules: []
scopes:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Πάτρα"]
    sources: []
""",
        encoding="utf-8",
    )
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "eshidis_id": "12345",
                        "title": "Ανάπλαση στην Πάτρα",
                        "authority_name": "Δήμος Πατρέων",
                        "submission_deadline": "01-08-2026 10:00:00",
                        "published_at": "01-07-2026 10:00:00",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_expanded_report(
        sources_config_path=config_path,
        eshidis_candidates_path=candidates_path,
        kimdis_pages=0,
    )

    assert report["summary"]["total_candidates"] == 1
    assert report["summary"]["focus_candidates"] == 1
    assert report["focus_candidates"][0]["official_id"] == "12345"
    assert report["focus_candidates"][0]["status_reason"]


def test_render_expanded_report_markdown_mentions_no_title_merge() -> None:
    markdown = render_expanded_report_markdown(
        {
            "checked_at": "2026-07-17T00:00:00+00:00",
            "as_of_date": "2026-07-17",
            "summary": {
                "total_candidates": 0,
                "focus_candidates": 0,
                "focus_open_proc_candidates": 0,
                "focus_expired_proc_candidates": 0,
                "focus_historical_awrd_symv_records": 0,
                "eshidis_candidates": 0,
                "kimdis_candidates": 0,
                "errors": 0,
            },
            "focus_open_proc_candidates": [],
            "focus_candidates": [],
            "all_candidates": [],
            "errors": [],
        }
    )

    assert "Expanded Tender Discovery Report" in markdown
    assert "title-only merge is disabled" in markdown


def test_short_alias_does_not_match_inside_unrelated_word(tmp_path) -> None:
    config_path = tmp_path / "sources.yml"
    config_path.write_text(
        """
version: 1
global_sources: []
collection_order: []
rules: []
scopes:
  - id: patras
    name: "Δήμος Πατρέων"
    aliases: ["Ρίο"]
    sources: []
""",
        encoding="utf-8",
    )
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "eshidis_id": "12345",
                        "title": "Επισκευή κτιρίου σχολείου",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_expanded_report(
        sources_config_path=config_path,
        eshidis_candidates_path=candidates_path,
        kimdis_pages=0,
    )

    assert report["summary"]["total_candidates"] == 1
    assert report["summary"]["focus_candidates"] == 0


def test_kimdis_proc_future_deadline_is_open_candidate(tmp_path) -> None:
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
    aliases: ["Ναυπακτίας"]
    sources: []
""",
        encoding="utf-8",
    )

    payload = {
        "content": [
            {
                "referenceNumber": "26PROC000000001",
                "title": "Συντήρηση οδών Δήμου Ναυπακτίας",
                "organization": {"value": "ΔΗΜΟΣ ΝΑΥΠΑΚΤΙΑΣ"},
                "finalSubmissionDate": "2026-08-01T10:00:00",
                "totalCostWithVAT": 1000,
                "cancelled": False,
            }
        ]
    }

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    with patch("tender_radar.sources.expanded_report.urlopen", return_value=Response()):
        report = build_expanded_report(
            sources_config_path=config_path,
            eshidis_candidates_path=None,
            kimdis_pages=1,
            as_of=date(2026, 7, 17),
        )

    assert report["summary"]["focus_open_proc_candidates"] == 1
    assert report["focus_open_proc_candidates"][0]["status"] == "SUBMISSION_OPEN_CANDIDATE"
