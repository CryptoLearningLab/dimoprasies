from pathlib import Path

from tender_radar.db import SearchableDocument
from tender_radar.evaluation import (
    EvaluationProfile,
    EvaluationRule,
    evaluate_documents,
    load_evaluation_profile,
    save_evaluation_config,
)


def test_evaluation_numeric_threshold_matches_budget_item() -> None:
    profile = EvaluationProfile(
        profile_id="test",
        name="Test",
        rules=(
            EvaluationRule(
                rule_id="foundation_excavation_price_gt_5",
                label="Foundation excavation unit price greater than 5 EUR",
                document_types={"budget"},
                phrases=("εκσκαφές θεμελίων",),
                numeric_operator=">",
                numeric_threshold=5.0,
                score=4.0,
                severity="important",
            ),
        ),
    )
    document = SearchableDocument(
        tender_id=1,
        eshidis_id="221999",
        tender_title="Tender",
        document_id=10,
        attachment_id=20,
        document_type="budget",
        original_name="budget.pdf",
        local_path="budget.pdf",
        text_sample="Α.Τ. 1 Εκσκαφές θεμελίων τιμή μονάδας 6,25 ευρώ ανά m3",
        text_path=None,
    )

    evaluations = evaluate_documents(profile, [document])

    assert len(evaluations) == 1
    assert evaluations[0].total_score == 4.0
    assert evaluations[0].hits[0].numeric_value == 6.25


def test_evaluation_numeric_threshold_rejects_low_price() -> None:
    profile = EvaluationProfile(
        profile_id="test",
        name="Test",
        rules=(
            EvaluationRule(
                rule_id="foundation_excavation_price_gt_5",
                label="Foundation excavation unit price greater than 5 EUR",
                document_types={"budget"},
                phrases=("εκσκαφές θεμελίων",),
                numeric_operator=">",
                numeric_threshold=5.0,
                score=4.0,
                severity="important",
            ),
        ),
    )
    document = SearchableDocument(
        1,
        "221999",
        "Tender",
        10,
        20,
        "budget",
        "budget.pdf",
        None,
        "Εκσκαφές θεμελίων 4,50 ευρώ",
        None,
    )

    evaluations = evaluate_documents(profile, [document])

    assert evaluations == []


def test_load_evaluation_profile_from_yaml() -> None:
    profile = load_evaluation_profile(Path("config/evaluation_profiles/public_works_dynamic.yml"))

    assert profile.profile_id == "public_works_dynamic"
    assert any(rule.rule_id == "foundation_excavation_price_gt_5" for rule in profile.rules)


def test_save_evaluation_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "dynamic.yml"

    saved = save_evaluation_config(
        path,
        {
            "profile": {"id": "dynamic", "name": "Dynamic"},
            "rules": [
                {
                    "id": "excavation_gt_5",
                    "label": "Εκσκαφές > 5",
                    "severity": "important",
                    "score": 4,
                    "document_types": ["budget"],
                    "phrases": ["εκσκαφές θεμελίων"],
                    "numeric": {"operator": ">", "threshold": 5},
                }
            ],
        },
    )

    loaded = load_evaluation_profile(path)

    assert saved["rules"][0]["numeric"]["threshold"] == 5.0
    assert loaded.rules[0].rule_id == "excavation_gt_5"
    assert loaded.rules[0].phrases == ("εκσκαφές θεμελίων",)
