from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import json
from pathlib import Path
import ssl
from typing import Any
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tender_radar.config import load_config
from tender_radar.sources.authority import discover_authority_candidates


KIMDIS_FAMILIES = {
    "khmdhs_notice": {
        "record_type": "PROC",
        "url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice?page={page}",
        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice/attachment/{reference}",
    },
    "khmdhs_auction": {
        "record_type": "AWRD",
        "url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction?page={page}",
        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction/attachment/{reference}",
    },
    "khmdhs_contract": {
        "record_type": "SYMV",
        "url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract?page={page}",
        "attachment_url": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract/attachment/{reference}",
    },
}


@dataclass(frozen=True)
class ExpandedTenderCandidate:
    source: str
    record_type: str
    official_id: str
    title: str | None
    authority: str | None
    budget: str | None
    published_at: str | None
    submission_deadline: str | None
    source_url: str
    attachment_url: str | None
    matched_scopes: list[str]
    match_notes: list[str]
    status: str
    status_reason: str
    source_id: str | None = None
    attachment_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_expanded_report(
    *,
    sources_config_path: Path,
    eshidis_candidates_path: Path | None,
    kimdis_pages: int = 5,
    authority_limit_per_source: int = 20,
    timeout_seconds: int = 20,
    allow_insecure_tls: bool = False,
    as_of: date | None = None,
    previous_report_path: Path | None = None,
    kimdis_source_ids: set[str] | None = None,
    authority_source_ids: set[str] | None = None,
) -> dict[str, Any]:
    sources_config = load_config(sources_config_path)
    scope_aliases = _scope_aliases(sources_config)
    checked_at = datetime.now(timezone.utc).isoformat()
    as_of_date = as_of or date.today()
    candidates: list[ExpandedTenderCandidate] = []
    errors: list[dict[str, object]] = []
    skipped_source_pages: list[dict[str, object]] = []
    previous_report = _load_previous_report(previous_report_path)

    if eshidis_candidates_path and eshidis_candidates_path.exists():
        payload = json.loads(eshidis_candidates_path.read_text(encoding="utf-8"))
        candidates.extend(_eshidis_candidates(payload, scope_aliases))
    elif eshidis_candidates_path:
        errors.append(
            {
                "source": "ESHIDIS",
                "path": str(eshidis_candidates_path),
                "message": "ESHIDIS candidates report not found.",
            }
        )

    kimdis_candidates, kimdis_errors, kimdis_page_stats = _fetch_kimdis_candidates(
        scope_aliases,
        pages=kimdis_pages,
        timeout_seconds=timeout_seconds,
        allow_insecure_tls=allow_insecure_tls,
        as_of=as_of_date,
        source_ids=kimdis_source_ids,
    )
    candidates.extend(kimdis_candidates)
    errors.extend(kimdis_errors)
    if kimdis_source_ids is not None:
        candidates.extend(_cached_candidates(previous_report, source="KIMDIS", skipped_source_ids=set(KIMDIS_FAMILIES) - kimdis_source_ids))
        skipped_source_pages.extend(
            _skipped_kimdis_source_pages(set(KIMDIS_FAMILIES) - kimdis_source_ids, previous_report=previous_report)
        )

    authority_candidates, authority_errors, authority_page_stats = discover_authority_candidates(
        sources_config,
        timeout_seconds=timeout_seconds,
        allow_insecure_tls=allow_insecure_tls,
        limit_per_source=authority_limit_per_source,
        source_ids=authority_source_ids,
    )
    for candidate in authority_candidates:
        candidates.append(
            ExpandedTenderCandidate(
                source="AUTHORITY",
                record_type=candidate.record_type,
                official_id=candidate.official_id,
                title=candidate.title,
                authority=candidate.authority,
                budget=None,
                published_at=candidate.published_at,
                submission_deadline=candidate.submission_deadline,
                source_url=candidate.detail_url or candidate.source_url,
                attachment_url=candidate.attachment_url,
                matched_scopes=[candidate.scope_name] if candidate.scope_name else _matched_scopes(candidate.to_dict(), scope_aliases),
                match_notes=[f"{candidate.source_name}: {candidate.parser_status}"],
                status=candidate.status,
                status_reason=candidate.status_reason,
                source_id=candidate.source_id,
                attachment_urls=candidate.attachment_urls,
            )
        )
    errors.extend(authority_errors)
    if authority_source_ids is not None:
        all_authority_source_ids = {
            str(source.get("id") or "")
            for source in sources_config.get("authority_adapters") or []
            if isinstance(source, dict) and source.get("id")
        }
        skipped_authority_source_ids = all_authority_source_ids - authority_source_ids
        candidates.extend(_cached_candidates(previous_report, source="AUTHORITY", skipped_source_ids=skipped_authority_source_ids))
        skipped_source_pages.extend(
            _skipped_authority_source_pages(
                sources_config,
                skipped_source_ids=skipped_authority_source_ids,
                previous_report=previous_report,
            )
        )

    unique_candidates = _dedupe_by_official_source_id(candidates)
    focus_candidates = [candidate for candidate in unique_candidates if candidate.matched_scopes]
    focus_open_proc = [
        candidate
        for candidate in focus_candidates
        if candidate.record_type == "PROC" and candidate.status == "SUBMISSION_OPEN_CANDIDATE"
    ]
    focus_authority_candidates = [candidate for candidate in focus_candidates if candidate.source == "AUTHORITY"]
    return {
        "checked_at": checked_at,
        "as_of_date": as_of_date.isoformat(),
        "sources_config_path": str(sources_config_path),
        "eshidis_candidates_path": str(eshidis_candidates_path) if eshidis_candidates_path else None,
        "kimdis_pages": kimdis_pages,
        "authority_limit_per_source": authority_limit_per_source,
        "summary": {
            "total_candidates": len(unique_candidates),
            "focus_candidates": len(focus_candidates),
            "eshidis_candidates": sum(1 for item in unique_candidates if item.source == "ESHIDIS"),
            "kimdis_candidates": sum(1 for item in unique_candidates if item.source == "KIMDIS"),
            "authority_candidates": sum(1 for item in unique_candidates if item.source == "AUTHORITY"),
            "focus_open_proc_candidates": len(focus_open_proc),
            "focus_authority_candidates": len(focus_authority_candidates),
            "focus_expired_proc_candidates": sum(
                1
                for item in focus_candidates
                if item.record_type == "PROC" and item.status == "SUBMISSION_EXPIRED_CANDIDATE"
            ),
            "focus_historical_awrd_symv_records": sum(
                1 for item in focus_candidates if item.record_type in {"AWRD", "SYMV"}
            ),
            "errors": len(errors),
        },
        "focus_open_proc_candidates": [candidate.to_dict() for candidate in focus_open_proc],
        "focus_authority_candidates": [candidate.to_dict() for candidate in focus_authority_candidates],
        "focus_candidates": [candidate.to_dict() for candidate in focus_candidates],
        "all_candidates": [candidate.to_dict() for candidate in unique_candidates],
        "source_pages": [*kimdis_page_stats, *authority_page_stats, *skipped_source_pages],
        "errors": errors,
        "deduplication": {
            "method": "official source id only",
            "title_only_merge": False,
        },
    }


def write_expanded_report(report: dict[str, Any], report_path: Path, markdown_path: Path | None = None) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_expanded_report_markdown(report), encoding="utf-8")


def render_expanded_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    focus = report.get("focus_candidates") if isinstance(report.get("focus_candidates"), list) else []
    all_candidates = report.get("all_candidates") if isinstance(report.get("all_candidates"), list) else []
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Expanded Tender Discovery Report",
        "",
        f"- Checked at: `{report.get('checked_at')}`",
        f"- As-of date: `{report.get('as_of_date')}`",
        f"- Total candidates: `{summary.get('total_candidates', 0)}`",
        f"- Focus candidates: `{summary.get('focus_candidates', 0)}`",
        f"- Focus open PROC candidates: `{summary.get('focus_open_proc_candidates', 0)}`",
        f"- Focus expired PROC candidates: `{summary.get('focus_expired_proc_candidates', 0)}`",
        f"- Focus historical AWRD/SYMV records: `{summary.get('focus_historical_awrd_symv_records', 0)}`",
        f"- ESHIDIS candidates: `{summary.get('eshidis_candidates', 0)}`",
        f"- KIMDIS candidates: `{summary.get('kimdis_candidates', 0)}`",
        f"- Authority candidates: `{summary.get('authority_candidates', 0)}`",
        f"- Errors: `{summary.get('errors', 0)}`",
        "- Deduplication: official source id only; title-only merge is disabled.",
        "",
        "## Focus Open PROC Candidates",
        "",
    ]
    open_proc = report.get("focus_open_proc_candidates") if isinstance(report.get("focus_open_proc_candidates"), list) else []
    if open_proc:
        lines.extend(_candidate_table(open_proc))
    else:
        lines.append("No focus-area PROC candidates with a future final submission date were found.")
    lines.extend([
        "",
        "## Focus Area Candidates",
        "",
    ])
    if focus:
        lines.extend(_candidate_table(focus))
    else:
        lines.append("No focus-area candidates were found in this controlled pass.")
    authority = report.get("focus_authority_candidates") if isinstance(report.get("focus_authority_candidates"), list) else []
    lines.extend(["", "## Authority Website Candidates", ""])
    if authority:
        lines.extend(_candidate_table(authority))
    else:
        lines.append("No focus-area authority website candidates were extracted.")
    lines.extend(["", "## All Candidates", ""])
    lines.extend(_candidate_table(all_candidates[:100]) if all_candidates else ["No candidates found."])
    if errors:
        lines.extend(["", "## Runtime Errors", ""])
        for error in errors:
            lines.append(f"- `{_cell(error.get('source') or '')}`: {_cell(error.get('message') or '')}")
    return "\n".join(lines) + "\n"


def _fetch_kimdis_candidates(
    scope_aliases: dict[str, list[str]],
    *,
    pages: int,
    timeout_seconds: int,
    allow_insecure_tls: bool,
    as_of: date,
    source_ids: set[str] | None = None,
) -> tuple[list[ExpandedTenderCandidate], list[dict[str, object]], list[dict[str, object]]]:
    context = ssl._create_unverified_context() if allow_insecure_tls else None
    candidates: list[ExpandedTenderCandidate] = []
    errors: list[dict[str, object]] = []
    page_stats: list[dict[str, object]] = []
    body = json.dumps({"contractType": "10"}).encode("utf-8")
    for source_id, family in KIMDIS_FAMILIES.items():
        if source_ids is not None and source_id not in source_ids:
            continue
        for page in range(max(0, pages)):
            url = str(family["url"]).format(page=page)
            request = Request(
                url,
                data=body,
                headers={
                    "User-Agent": "TenderRadar/0.1 expanded-report",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=timeout_seconds, context=context) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                errors.append({"source": source_id, "url": url, "message": str(exc)})
                page_stats.append(
                    {
                        "source": source_id,
                        "record_type": family["record_type"],
                        "page": page,
                        "items_returned": None,
                        "error": str(exc),
                    }
                )
                continue
            content = payload.get("content") or []
            page_stats.append(
                {
                    "source": source_id,
                    "record_type": family["record_type"],
                    "page": page,
                    "items_returned": len(content) if isinstance(content, list) else 0,
                    "error": None,
                }
            )
            for item in content:
                if not isinstance(item, dict):
                    continue
                reference = str(item.get("referenceNumber") or "")
                if not reference:
                    continue
                status, status_reason = _kimdis_status(item, str(family["record_type"]), as_of)
                attachment_url = str(family["attachment_url"]).format(reference=reference)
                candidates.append(
                    ExpandedTenderCandidate(
                        source="KIMDIS",
                        record_type=str(family["record_type"]),
                        official_id=reference,
                        title=_none_or_str(item.get("title")),
                        authority=_organization_name(item),
                        budget=_budget(item),
                        published_at=_none_or_str(item.get("submissionDate") or item.get("signedDate")),
                        submission_deadline=_none_or_str(item.get("finalSubmissionDate")),
                        source_url=url,
                        attachment_url=attachment_url,
                        matched_scopes=_matched_scopes(item, scope_aliases),
                        match_notes=_match_notes(item, scope_aliases),
                        status=status,
                        status_reason=status_reason,
                        source_id=source_id,
                        attachment_urls=[attachment_url],
                    )
                )
    return candidates, errors, page_stats


def _eshidis_candidates(payload: dict[str, Any], scope_aliases: dict[str, list[str]]) -> list[ExpandedTenderCandidate]:
    candidates: list[ExpandedTenderCandidate] = []
    for item in payload.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        eshidis_id = str(item.get("eshidis_id") or "")
        if not eshidis_id:
            continue
        candidates.append(
            ExpandedTenderCandidate(
                source="ESHIDIS",
                record_type="ESHIDIS",
                official_id=eshidis_id,
                title=_none_or_str(item.get("title")),
                authority=_none_or_str(item.get("authority_name")),
                budget=_budget(item),
                published_at=_none_or_str(item.get("published_at")),
                submission_deadline=_none_or_str(item.get("submission_deadline")),
                source_url=f"https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{eshidis_id}",
                attachment_url=None,
                matched_scopes=_matched_scopes(item, scope_aliases),
                match_notes=_match_notes(item, scope_aliases),
                status=str(item.get("status") or "DISCOVERED_ACTIVE_CANDIDATE"),
                status_reason="ESHIDIS discovery candidate; detail/status verification remains separate.",
                source_id="eshidis_active_search",
            )
        )
    return candidates


def _load_previous_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _cached_candidates(
    previous_report: dict[str, Any] | None,
    *,
    source: str,
    skipped_source_ids: set[str],
) -> list[ExpandedTenderCandidate]:
    if not previous_report or not skipped_source_ids:
        return []
    cached: list[ExpandedTenderCandidate] = []
    for item in previous_report.get("all_candidates") or []:
        if not isinstance(item, dict) or item.get("source") != source:
            continue
        source_id = _candidate_source_id(item)
        if source_id and source_id not in skipped_source_ids:
            continue
        if source_id is None and source == "KIMDIS" and _kimdis_source_id_for_record_type(str(item.get("record_type") or "")) not in skipped_source_ids:
            continue
        cached.append(_candidate_from_dict(item, cached=True))
    return cached


def _candidate_from_dict(item: dict[str, Any], *, cached: bool = False) -> ExpandedTenderCandidate:
    match_notes = [str(note) for note in item.get("match_notes") or []]
    if cached and "SKIPPED_UNCHANGED cached from previous report" not in match_notes:
        match_notes.append("SKIPPED_UNCHANGED cached from previous report")
    return ExpandedTenderCandidate(
        source=str(item.get("source") or ""),
        record_type=str(item.get("record_type") or ""),
        official_id=str(item.get("official_id") or ""),
        title=_none_or_str(item.get("title")),
        authority=_none_or_str(item.get("authority")),
        budget=_none_or_str(item.get("budget")),
        published_at=_none_or_str(item.get("published_at")),
        submission_deadline=_none_or_str(item.get("submission_deadline")),
        source_url=str(item.get("source_url") or ""),
        attachment_url=_none_or_str(item.get("attachment_url")),
        matched_scopes=[str(value) for value in item.get("matched_scopes") or []],
        match_notes=match_notes,
        status=str(item.get("status") or "UNKNOWN"),
        status_reason=str(item.get("status_reason") or ""),
        source_id=_candidate_source_id(item),
        attachment_urls=[str(value) for value in item.get("attachment_urls") or []],
    )


def _candidate_source_id(item: dict[str, Any]) -> str | None:
    value = item.get("source_id")
    if value not in (None, ""):
        return str(value)
    if item.get("source") == "KIMDIS":
        return _kimdis_source_id_for_record_type(str(item.get("record_type") or ""))
    return None


def _kimdis_source_id_for_record_type(record_type: str) -> str | None:
    for source_id, family in KIMDIS_FAMILIES.items():
        if family["record_type"] == record_type:
            return source_id
    return None


def _skipped_kimdis_source_pages(
    skipped_source_ids: set[str],
    *,
    previous_report: dict[str, Any] | None,
) -> list[dict[str, object]]:
    counts = _previous_counts_by_source(previous_report)
    return [
        {
            "source": source_id,
            "record_type": KIMDIS_FAMILIES[source_id]["record_type"],
            "page": None,
            "items_returned": counts.get(source_id, 0),
            "error": None,
            "status": "SKIPPED_UNCHANGED",
        }
        for source_id in sorted(skipped_source_ids)
    ]


def _skipped_authority_source_pages(
    config: dict[str, Any],
    *,
    skipped_source_ids: set[str],
    previous_report: dict[str, Any] | None,
) -> list[dict[str, object]]:
    counts = _previous_counts_by_source(previous_report)
    sources = {
        str(source.get("id") or ""): source
        for source in config.get("authority_adapters") or []
        if isinstance(source, dict) and source.get("id")
    }
    return [
        {
            "source": source_id,
            "adapter": sources.get(source_id, {}).get("adapter"),
            "url": sources.get(source_id, {}).get("url"),
            "items_returned": counts.get(source_id, 0),
            "error": None,
            "status": "SKIPPED_UNCHANGED",
        }
        for source_id in sorted(skipped_source_ids)
    ]


def _previous_counts_by_source(previous_report: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not previous_report:
        return counts
    for item in previous_report.get("all_candidates") or []:
        if not isinstance(item, dict):
            continue
        source_id = _candidate_source_id(item)
        if not source_id:
            continue
        counts[source_id] = counts.get(source_id, 0) + 1
    return counts


def _scope_aliases(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scopes: dict[str, dict[str, Any]] = {}
    for scope in config.get("scopes") or []:
        if not isinstance(scope, dict):
            continue
        name = str(scope.get("name") or scope.get("id") or "")
        aliases = [_normalize_text(str(alias)) for alias in scope.get("aliases") or [] if str(alias).strip()]
        ambiguous_aliases = []
        for item in scope.get("ambiguous_aliases") or []:
            if not isinstance(item, dict) or not str(item.get("alias") or "").strip():
                continue
            ambiguous_aliases.append(
                {
                    "alias": _normalize_text(str(item.get("alias"))),
                    "positive_context": [
                        _normalize_text(str(value)) for value in item.get("positive_context") or [] if str(value).strip()
                    ],
                    "negative_context": [
                        _normalize_text(str(value)) for value in item.get("negative_context") or [] if str(value).strip()
                    ],
                }
            )
        scopes[name] = {"aliases": aliases, "ambiguous_aliases": ambiguous_aliases}
    return scopes


def _matched_scopes(item: dict[str, Any], scope_aliases: dict[str, dict[str, Any]]) -> list[str]:
    return [match["scope"] for match in _scope_matches(item, scope_aliases)]


def _match_notes(item: dict[str, Any], scope_aliases: dict[str, dict[str, Any]]) -> list[str]:
    return [match["note"] for match in _scope_matches(item, scope_aliases) if match.get("note")]


def _scope_matches(item: dict[str, Any], scope_aliases: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    haystack = _normalize_text(json.dumps(item, ensure_ascii=False))
    tokens = set(_tokens(haystack))
    matches: list[dict[str, str]] = []
    for scope, config in scope_aliases.items():
        aliases = config.get("aliases") or []
        if any(_alias_matches(str(alias), haystack, tokens) for alias in aliases):
            matches.append({"scope": scope, "note": ""})
            continue
        for rule in config.get("ambiguous_aliases") or []:
            if not _alias_matches(str(rule.get("alias") or ""), haystack, tokens):
                continue
            negative_context = rule.get("negative_context") or []
            if any(_alias_matches(str(value), haystack, tokens) for value in negative_context):
                continue
            positive_context = rule.get("positive_context") or []
            if any(_alias_matches(str(value), haystack, tokens) for value in positive_context):
                matches.append({"scope": scope, "note": f"ambiguous alias confirmed by context: {rule.get('alias')}"})
            else:
                matches.append({"scope": scope, "note": f"ambiguous alias retained for review: {rule.get('alias')}"})
            break
    return matches


def _dedupe_by_official_source_id(candidates: list[ExpandedTenderCandidate]) -> list[ExpandedTenderCandidate]:
    seen: set[tuple[str, str, str]] = set()
    selected: list[ExpandedTenderCandidate] = []
    for candidate in candidates:
        key = (candidate.source, candidate.record_type, candidate.official_id)
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    return selected


def _candidate_table(candidates: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Source | Type | Official id | Status | Title | Authority | Budget | Deadline | Scope | Notes | Link |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        link = item.get("source_url") or item.get("attachment_url") or ""
        lines.append(
            "| {source} | {kind} | `{official_id}` | `{status}` | {title} | {authority} | {budget} | {deadline} | {scope} | {notes} | {link} |".format(
                source=_cell(item.get("source") or ""),
                kind=_cell(item.get("record_type") or ""),
                official_id=_cell(item.get("official_id") or ""),
                status=_cell(item.get("status") or ""),
                title=_cell(item.get("title") or ""),
                authority=_cell(item.get("authority") or ""),
                budget=_cell(item.get("budget") or ""),
                deadline=_cell(item.get("submission_deadline") or ""),
                scope=_cell(", ".join(item.get("matched_scopes") or [])),
                notes=_cell(", ".join(item.get("match_notes") or [])),
                link=_cell(link),
            )
        )
    return lines


def _organization_name(item: dict[str, Any]) -> str | None:
    organization = item.get("organization")
    if isinstance(organization, dict):
        return _none_or_str(organization.get("value") or organization.get("name"))
    return _none_or_str(item.get("organizationName") or item.get("authorityName"))


def _budget(item: dict[str, Any]) -> str | None:
    for key in ("budget", "totalCostWithVAT", "totalCostWithoutVAT", "totalCost", "estimatedValue", "estTotalCost", "awardTotalCost"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    row_text = item.get("row_text")
    if isinstance(row_text, str):
        return _extract_budget_from_text(row_text)
    return None


def _extract_budget_from_text(text: str) -> str | None:
    import re

    match = re.search(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", text)
    return match.group(0) if match else None


def _none_or_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:180]


def _kimdis_status(item: dict[str, Any], record_type: str, as_of: date) -> tuple[str, str]:
    if record_type == "AWRD":
        return "HISTORICAL_AWARD_RECORD", "AWRD records are award/assignment stage, not submission stage."
    if record_type == "SYMV":
        return "HISTORICAL_CONTRACT_RECORD", "SYMV records are signed contract stage, not submission stage."
    if item.get("cancelled") is True:
        return "CANCELLED_NOTICE", "KIMDIS notice is marked cancelled."
    deadline = _parse_iso_datetime(item.get("finalSubmissionDate"))
    if deadline is None:
        return "UNKNOWN_DEADLINE_CANDIDATE", "KIMDIS PROC notice has no parsable finalSubmissionDate."
    if deadline.date() > as_of:
        return "SUBMISSION_OPEN_CANDIDATE", f"finalSubmissionDate {deadline.isoformat()} is after {as_of.isoformat()}."
    return "SUBMISSION_EXPIRED_CANDIDATE", f"finalSubmissionDate {deadline.isoformat()} is on or before {as_of.isoformat()}."


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _alias_matches(alias: str, haystack: str, tokens: set[str]) -> bool:
    alias_tokens = _tokens(alias)
    if not alias_tokens:
        return False
    if len(alias_tokens) == 1:
        token = alias_tokens[0]
        return token in tokens if len(token) <= 4 else token in tokens or f" {token} " in f" {haystack} "
    return " ".join(alias_tokens) in haystack


def _tokens(value: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9α-ω]+", value)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", without_accents)
