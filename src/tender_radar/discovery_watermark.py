from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


KIMDIS_FAMILY_BY_RECORD_TYPE = {
    "PROC": "kimdis_proc",
    "AWRD": "kimdis_awrd",
    "SYMV": "kimdis_symv",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_discovery_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "runs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "runs": []}
    if not isinstance(payload, dict):
        return {"version": 1, "runs": []}
    runs = payload.get("runs") if isinstance(payload.get("runs"), list) else []
    return {"version": int(payload.get("version") or 1), "runs": runs}


def append_discovery_run(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    history = load_discovery_history(path)
    runs = [run for run in history.get("runs", []) if isinstance(run, dict)]
    runs.append(record)
    history = {"version": 1, "runs": runs[-200:]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def latest_discovery_run(path: Path) -> dict[str, Any] | None:
    runs = load_discovery_history(path).get("runs", [])
    for run in reversed(runs):
        if isinstance(run, dict):
            return run
    return None


def latest_successful_discovery_run(path: Path) -> dict[str, Any] | None:
    runs = load_discovery_history(path).get("runs", [])
    for run in reversed(runs):
        if isinstance(run, dict) and run.get("success") is True:
            return run
    return None


def build_discovery_run_record(
    *,
    started_at: str,
    completed_at: str,
    mode: str,
    eshidis_limit: int,
    kimdis_pages: int,
    command_results: list[dict[str, Any]],
    eshidis_report_path: Path,
    expanded_report_path: Path,
    previous_success: dict[str, Any] | None,
    max_eshidis_limit: int | None = None,
    max_kimdis_pages: int | None = None,
) -> dict[str, Any]:
    eshidis_report = _read_json(eshidis_report_path)
    expanded_report = _read_json(expanded_report_path)
    source_families = _source_families(
        eshidis_report=eshidis_report,
        expanded_report=expanded_report,
        eshidis_limit=eshidis_limit,
        kimdis_pages=kimdis_pages,
    )
    command_failures = [
        {
            "name": item.get("name"),
            "returncode": item.get("returncode"),
            "stderr": item.get("stderr"),
        }
        for item in command_results
        if item.get("returncode") not in (0, None)
    ]
    source_errors = [
        {"family": family, **error}
        for family, data in source_families.items()
        for error in data.get("errors", [])
        if isinstance(error, dict)
    ]
    watermark = _watermark_status(source_families, previous_success)
    if mode == "backfill" and not watermark["complete"]:
        if max_eshidis_limit is not None and max_kimdis_pages is not None:
            if eshidis_limit >= max_eshidis_limit and kimdis_pages >= max_kimdis_pages:
                watermark["stop_reason"] = "MAX_BACKFILL_DEPTH_REACHED"
    source_success = not command_failures and not source_errors
    success = source_success and bool(watermark.get("complete"))
    return {
        "run_id": uuid.uuid4().hex,
        "started_at": started_at,
        "completed_at": completed_at,
        "mode": mode,
        "success": success,
        "source_success": source_success,
        "partial_failures": [*command_failures, *source_errors],
        "depth": {
            "eshidis_limit": eshidis_limit,
            "kimdis_pages_per_family": kimdis_pages,
        },
        "source_families": source_families,
        "watermark": watermark,
        "candidate_ids": sorted(
            {
                candidate_id
                for family in source_families.values()
                for candidate_id in family.get("candidate_ids", [])
                if isinstance(candidate_id, str)
            }
        ),
        "reports": {
            "eshidis_candidates": str(eshidis_report_path),
            "expanded_report": str(expanded_report_path),
        },
        "status_note": "Discovery remains candidate-only; this run never emits VERIFIED_ACTIVE.",
    }


def _source_families(
    *,
    eshidis_report: dict[str, Any],
    expanded_report: dict[str, Any],
    eshidis_limit: int,
    kimdis_pages: int,
) -> dict[str, dict[str, Any]]:
    eshidis_candidates = eshidis_report.get("candidates") if isinstance(eshidis_report.get("candidates"), list) else []
    eshidis_errors = []
    if eshidis_report.get("navigation_error"):
        eshidis_errors.append({"source": "eshidis_active", "message": eshidis_report.get("navigation_error")})
    families: dict[str, dict[str, Any]] = {
        "eshidis_active": {
            "source": "ESHIDIS",
            "record_type": "ESHIDIS",
            "depth": {"limit": eshidis_limit},
            "candidate_ids": _ids_from_items(eshidis_candidates, "eshidis_id"),
            "errors": eshidis_errors,
            "exhausted": len(eshidis_candidates) < eshidis_limit,
        }
    }
    all_candidates = expanded_report.get("all_candidates")
    if not isinstance(all_candidates, list):
        all_candidates = []
    errors = expanded_report.get("errors")
    if not isinstance(errors, list):
        errors = []
    page_stats = expanded_report.get("source_pages")
    if not isinstance(page_stats, list):
        page_stats = []
    for record_type, family_id in KIMDIS_FAMILY_BY_RECORD_TYPE.items():
        family_candidates = [
            item
            for item in all_candidates
            if isinstance(item, dict) and item.get("source") == "KIMDIS" and item.get("record_type") == record_type
        ]
        family_errors = [
            error
            for error in errors
            if isinstance(error, dict) and _kimdis_error_family(str(error.get("source") or "")) == family_id
        ]
        family_pages = [
            page
            for page in page_stats
            if isinstance(page, dict) and _kimdis_error_family(str(page.get("source") or "")) == family_id
        ]
        families[family_id] = {
            "source": "KIMDIS",
            "record_type": record_type,
            "depth": {"pages": kimdis_pages},
            "candidate_ids": _ids_from_items(family_candidates, "official_id"),
            "errors": family_errors,
            "exhausted": any(page.get("items_returned") == 0 for page in family_pages),
            "pages": family_pages,
        }
    return families


def _watermark_status(
    source_families: dict[str, dict[str, Any]],
    previous_success: dict[str, Any] | None,
) -> dict[str, Any]:
    if not previous_success:
        return {
            "previous_run_id": None,
            "complete": True,
            "stop_reason": "NO_PREVIOUS_SUCCESSFUL_RUN_BASELINE",
            "families": {},
        }
    previous_families = (
        previous_success.get("source_families") if isinstance(previous_success.get("source_families"), dict) else {}
    )
    family_status: dict[str, dict[str, Any]] = {}
    complete = True
    for family_id, current in source_families.items():
        previous = previous_families.get(family_id) if isinstance(previous_families.get(family_id), dict) else {}
        previous_ids = set(str(value) for value in previous.get("candidate_ids") or [] if str(value).strip())
        current_ids = set(str(value) for value in current.get("candidate_ids") or [] if str(value).strip())
        overlap = sorted(previous_ids & current_ids)
        reached = bool(overlap) or not previous_ids
        exhausted = bool(current.get("exhausted"))
        family_complete = reached or exhausted
        complete = complete and family_complete
        family_status[family_id] = {
            "previous_candidate_count": len(previous_ids),
            "current_candidate_count": len(current_ids),
            "overlap_ids": overlap[:20],
            "reached_previous_window": reached,
            "source_exhausted": exhausted,
            "complete": family_complete,
        }
    return {
        "previous_run_id": previous_success.get("run_id"),
        "complete": complete,
        "stop_reason": "PREVIOUS_WINDOW_REACHED_OR_SOURCE_EXHAUSTED" if complete else "NEEDS_DEEPER_BACKFILL",
        "families": family_status,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ids_from_items(items: list[Any], key: str) -> list[str]:
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get(key) or "").strip()
        if value and value not in ids:
            ids.append(value)
    return ids


def _kimdis_error_family(source: str) -> str | None:
    return {
        "khmdhs_notice": "kimdis_proc",
        "khmdhs_auction": "kimdis_awrd",
        "khmdhs_contract": "kimdis_symv",
    }.get(source)
