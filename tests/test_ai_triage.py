import json
from unittest.mock import patch

from tender_radar.ai_triage import (
    build_ai_triage_report,
    deterministic_signals,
    _prompt_text,
    render_ai_triage_markdown,
)


def test_deterministic_signals_detect_public_works_and_admin_terms() -> None:
    works = deterministic_signals(
        {
            "official_id": "26PROC019417347",
            "title": "Διακήρυξη έργου αποκατάστασης οδοποιίας",
            "attachment_urls": ["https://example.test/file.pdf"],
        }
    )
    admin = deterministic_signals({"title": "ΑΝΑΚΟΙΝΩΣΗ ΣΟΧ 2/2026 για πρόσληψη προσωπικού"})

    assert works.has_kimdis_proc_id is True
    assert works.has_document_links is True
    assert works.public_works_terms
    assert admin.admin_drop_terms


def test_ai_triage_report_normalizes_openai_classifications() -> None:
    rows = [
        {"row_key": "221744", "source": "eshidis", "title": "Ασφαλτόστρωση δρόμου", "display_id": "221744"},
        {"row_key": "AUTH-1", "source": "authority", "title": "ΠΡΟΓΡΑΜΜΑ ΕΚΛΟΓΩΝ"},
    ]
    ai_result = [
        {
            "row_key": "221744",
            "decision": "KEEP_ACTIVE_TENDER",
            "confidence": 0.91,
            "reason": "Έχει Α/Α ΕΣΗΔΗΣ και τίτλο έργου.",
            "eshidis_id_candidates": ["221744"],
        },
        {
            "row_key": "AUTH-1",
            "decision": "DROP_ADMIN",
            "confidence": 0.95,
            "reason": "Διοικητική/εκλογική ανακοίνωση.",
            "eshidis_id_candidates": [],
        },
    ]

    with patch("tender_radar.ai_triage.load_openai_api_key", return_value="test-key"), patch(
        "tender_radar.ai_triage.classify_batch_with_openai", return_value=ai_result
    ):
        report = build_ai_triage_report(rows, batch_size=10)

    assert report["summary"]["kept_total"] == 1
    assert report["summary"]["dropped_total"] == 1
    assert report["rows"][0]["ai"]["keep_for_daily_review"] is True
    assert report["rows"][1]["ai"]["decision"] == "DROP_ADMIN"


def test_ai_triage_rejects_seven_digit_eshidis_hints() -> None:
    rows = [{"row_key": "AUTH-1", "source": "authority", "title": "Διακήρυξη έργου"}]
    ai_result = [
        {
            "row_key": "AUTH-1",
            "decision": "REVIEW_TENDER_CANDIDATE",
            "confidence": 0.7,
            "reason": "Έχει έργο αλλά ο αριθμός είναι ύποπτος.",
            "eshidis_id_candidates": ["221744", "1234567"],
        }
    ]

    with patch("tender_radar.ai_triage.load_openai_api_key", return_value="test-key"), patch(
        "tender_radar.ai_triage.classify_batch_with_openai", return_value=ai_result
    ):
        report = build_ai_triage_report(rows, batch_size=10)

    assert report["rows"][0]["ai"]["eshidis_id_candidates"] == ["221744"]


def test_ai_triage_clears_eshidis_hints_for_dropped_rows() -> None:
    rows = [{"row_key": "AUTH-1", "source": "authority", "title": "Υπηρεσίες εκπαίδευσης"}]
    ai_result = [
        {
            "row_key": "AUTH-1",
            "decision": "DROP_OUT_OF_SCOPE_SUPPLY_SERVICE",
            "confidence": 0.9,
            "reason": "Υπηρεσία εκπαίδευσης.",
            "eshidis_id_candidates": ["221744"],
        }
    ]

    with patch("tender_radar.ai_triage.load_openai_api_key", return_value="test-key"), patch(
        "tender_radar.ai_triage.classify_batch_with_openai", return_value=ai_result
    ):
        report = build_ai_triage_report(rows, batch_size=10)

    assert report["rows"][0]["ai"]["keep_for_daily_review"] is False
    assert report["rows"][0]["ai"]["eshidis_id_candidates"] == []


def test_ai_triage_prompt_excludes_observed_non_works_false_keeps() -> None:
    prompt = _prompt_text(
        [
            {
                "row_key": "AUTH-1",
                "title": "Πρόσκληση υπηρεσιών τεχνικού συμβούλου με απευθείας ανάθεση άρθρο 118",
            }
        ]
    )

    assert "technical-consultant services" in prompt
    assert "direct assignments" in prompt
    assert "supplies even with installation" in prompt
    assert "Do not use REVIEW_TENDER_CANDIDATE" in prompt


def test_ai_triage_markdown_contains_summary() -> None:
    markdown = render_ai_triage_markdown(
        {
            "generated_at": "2026-07-18T00:00:00+00:00",
            "model": "test-model",
            "input_rows": 1,
            "summary": {"kept_total": 1, "dropped_total": 0, "errors": 0},
            "rows": [
                {
                    "row_key": "221744",
                    "source": "eshidis",
                    "title": "Ασφαλτόστρωση",
                    "authority_name": "Δήμος",
                    "ai": {
                        "decision": "KEEP_ACTIVE_TENDER",
                        "confidence": 0.9,
                        "reason": "Διαγωνισμός έργου.",
                        "eshidis_id_candidates": ["221744"],
                    },
                }
            ],
        }
    )

    assert "AI Discovery Triage Report" in markdown
    assert "KEEP_ACTIVE_TENDER" in markdown
    assert "221744" in markdown
