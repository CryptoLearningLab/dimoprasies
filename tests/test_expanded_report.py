import json

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


def test_render_expanded_report_markdown_mentions_no_title_merge() -> None:
    markdown = render_expanded_report_markdown(
        {
            "checked_at": "2026-07-17T00:00:00+00:00",
            "summary": {
                "total_candidates": 0,
                "focus_candidates": 0,
                "eshidis_candidates": 0,
                "kimdis_candidates": 0,
                "errors": 0,
            },
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
