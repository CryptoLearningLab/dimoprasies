import json

from tender_radar.discovery_watermark import (
    append_discovery_run,
    build_discovery_run_record,
    latest_successful_discovery_run,
)


def test_discovery_run_record_reaches_previous_window_by_overlap(tmp_path) -> None:
    eshidis_report = tmp_path / "eshidis.json"
    expanded_report = tmp_path / "expanded.json"
    eshidis_report.write_text(json.dumps({"candidates": [{"eshidis_id": "221744"}]}), encoding="utf-8")
    expanded_report.write_text(
        json.dumps(
            {
                "all_candidates": [
                    {"source": "KIMDIS", "record_type": "PROC", "official_id": "26PROC000000001"},
                    {"source": "KIMDIS", "record_type": "AWRD", "official_id": "26AWRD000000001"},
                    {"source": "KIMDIS", "record_type": "SYMV", "official_id": "26SYMV000000001"},
                ],
                "source_pages": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    previous = {
        "run_id": "previous",
        "source_families": {
            "eshidis_active": {"candidate_ids": ["221744"]},
            "kimdis_proc": {"candidate_ids": ["26PROC000000001"]},
            "kimdis_awrd": {"candidate_ids": ["26AWRD000000001"]},
            "kimdis_symv": {"candidate_ids": ["26SYMV000000001"]},
        },
    }

    record = build_discovery_run_record(
        started_at="2026-07-18T00:00:00+00:00",
        completed_at="2026-07-18T00:01:00+00:00",
        mode="backfill",
        eshidis_limit=100,
        kimdis_pages=20,
        command_results=[{"name": "expanded_report", "returncode": 0}],
        eshidis_report_path=eshidis_report,
        expanded_report_path=expanded_report,
        previous_success=previous,
    )

    assert record["success"] is True
    assert record["watermark"]["complete"] is True
    assert record["watermark"]["previous_run_id"] == "previous"
    assert record["watermark"]["families"]["kimdis_proc"]["overlap_ids"] == ["26PROC000000001"]


def test_discovery_run_record_tracks_partial_failures_and_needs_backfill(tmp_path) -> None:
    eshidis_report = tmp_path / "eshidis.json"
    expanded_report = tmp_path / "expanded.json"
    eshidis_report.write_text(json.dumps({"candidates": [{"eshidis_id": "221800"}]}), encoding="utf-8")
    expanded_report.write_text(
        json.dumps(
            {
                "all_candidates": [{"source": "KIMDIS", "record_type": "PROC", "official_id": "26PROC000000002"}],
                "source_pages": [{"source": "khmdhs_notice", "record_type": "PROC", "page": 0, "items_returned": 50}],
                "errors": [{"source": "khmdhs_notice", "message": "timeout"}],
            }
        ),
        encoding="utf-8",
    )
    previous = {
        "run_id": "previous",
        "source_families": {
            "eshidis_active": {"candidate_ids": ["221744"]},
            "kimdis_proc": {"candidate_ids": ["26PROC000000001"]},
        },
    }

    record = build_discovery_run_record(
        started_at="2026-07-18T00:00:00+00:00",
        completed_at="2026-07-18T00:01:00+00:00",
        mode="backfill",
        eshidis_limit=100,
        kimdis_pages=20,
        command_results=[{"name": "expanded_report", "returncode": 0}],
        eshidis_report_path=eshidis_report,
        expanded_report_path=expanded_report,
        previous_success=previous,
    )

    assert record["success"] is False
    assert record["partial_failures"][0]["family"] == "kimdis_proc"
    assert record["watermark"]["complete"] is False
    assert record["watermark"]["stop_reason"] == "NEEDS_DEEPER_BACKFILL"


def test_discovery_history_returns_latest_successful_run(tmp_path) -> None:
    path = tmp_path / "runs.json"
    append_discovery_run(path, {"run_id": "failed", "success": False})
    append_discovery_run(path, {"run_id": "success", "success": True})

    assert latest_successful_discovery_run(path)["run_id"] == "success"
