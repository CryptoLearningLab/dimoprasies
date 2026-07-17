from pathlib import Path

import tender_radar.ui_server as ui_server
from tender_radar.ui_server import (
    content_type_for_path,
    dashboard_payload,
    format_budget,
    interest_reason,
    parse_budget_from_row_text,
    preview_kind,
    short_text_sample,
    focus_term_matches,
)


def test_report_json_content_type_includes_utf8_charset() -> None:
    assert content_type_for_path(Path("candidates.json")) == "application/json; charset=utf-8"


def test_report_markdown_content_type_includes_utf8_charset() -> None:
    assert content_type_for_path(Path("candidates.md")) == "text/markdown; charset=utf-8"


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
    assert payload["tenders"][0]["download_url"] == "https://example.test/attachment/26PROC000000001"
    assert payload["tenders"][0]["supports_eshidis_actions"] is False
    assert payload["tenders"][0]["deadline_display"] == "24-07-2026 13:00"


def test_interest_reason_uses_locations_config() -> None:
    assert interest_reason("Έργο στον Δήμο Πατρέων EL632") == "Δήμος Πατρέων"


def test_region_focus_uses_included_units_not_broad_nuts_prefix() -> None:
    assert interest_reason("Έργο στην Περιφερειακή Ενότητα Φωκίδας EL645") == "Περιφέρεια Στερεάς Ελλάδας - Φωκίδα"
    assert interest_reason("Έργο στη Φθιώτιδα EL644") is None


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
